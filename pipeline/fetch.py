from __future__ import annotations

import asyncio
import gzip
import json
from pathlib import Path

import httpx

from pipeline.config import Config
from pipeline.m3u import parse_m3u
from pipeline.models import Channel

_RETRIES = 3
_BACKOFF_BASE = 1.5


async def _get_with_retry(client: httpx.AsyncClient, url: str, *, retries: int = _RETRIES) -> httpx.Response:
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            r = await client.get(url, timeout=30)
            r.raise_for_status()
            return r
        except httpx.HTTPStatusError as e:
            last_exc = e
            if attempt < retries - 1:
                await asyncio.sleep(_BACKOFF_BASE ** attempt)
        except httpx.RequestError as e:
            last_exc = e
            if attempt < retries - 1:
                await asyncio.sleep(_BACKOFF_BASE ** attempt)
    assert last_exc is not None
    raise last_exc


async def fetch_channels(cfg: Config) -> list[Channel]:
    """Merge streams + channels + feeds into Channel records (one per stream URL)."""
    async with httpx.AsyncClient(http2=True, follow_redirects=True) as client:
        streams_r, channels_r, _categories_r, feeds_r = await asyncio.gather(
            _get_with_retry(client, cfg.iptv_org["streams"]),
            _get_with_retry(client, cfg.iptv_org["channels"]),
            _get_with_retry(client, cfg.iptv_org["categories"]),
            _get_with_retry(client, cfg.iptv_org["feeds"]),
        )

    streams = streams_r.json()
    channels_meta = {c["id"]: c for c in channels_r.json()}
    feed_res: dict[tuple[str, str | None], int | None] = {}
    for f in feeds_r.json():
        height = (f.get("video") or {}).get("height")
        feed_res[(f["channel"], f.get("id"))] = height

    out: list[Channel] = []
    for s in streams:
        cid = s["channel"]
        meta = channels_meta.get(cid)
        if meta is None:
            continue
        height = feed_res.get((cid, s.get("feed")))
        out.append(Channel(
            id=cid,
            name=meta["name"],
            url=s["url"],
            logo=meta.get("logo"),
            country=meta.get("country", ""),
            categories=list(meta.get("categories", [])),
            languages=list(meta.get("languages", [])),
            resolution_height=height,
        ))
    return out


async def fetch_epg_files(cfg: Config, out_dir: Path) -> dict[str, Path]:
    """Download each EPG xmltv.gz, decompress, write to out_dir/<code>.xml. Returns map code->path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    async with httpx.AsyncClient(http2=True, follow_redirects=True) as client:
        async def _one(code: str, url: str) -> None:
            r = await _get_with_retry(client, url)
            xml_bytes = gzip.decompress(r.content) if url.endswith(".gz") else r.content
            p = out_dir / f"{code.lower()}.xml"
            p.write_bytes(xml_bytes)
            paths[code] = p

        results = await asyncio.gather(
            *[_one(code, url) for code, url in cfg.epg_sources.items()],
            return_exceptions=True,
        )
        failures = [
            (code, result)
            for code, result in zip(cfg.epg_sources.keys(), results)
            if isinstance(result, BaseException)
        ]
        if failures and len(failures) == len(cfg.epg_sources):
            # All sources failed — surface to orchestrator. Partial failures are silent
            # so the surviving EPG entries still ship.
            codes = ", ".join(c for c, _ in failures)
            raise RuntimeError(f"all EPG sources failed: {codes}")
    return paths


async def fetch_playlist_channels(cfg: Config) -> list[Channel]:
    """Download and parse each external M3U in cfg.playlist_sources.

    Sources are independent: a single source failing is tolerated, but if every
    source fails the error is surfaced to the orchestrator (which treats it as
    non-fatal). Returns the concatenation of all parsed channels.
    """
    if not cfg.playlist_sources:
        return []

    async with httpx.AsyncClient(http2=True, follow_redirects=True) as client:
        results = await asyncio.gather(
            *[_get_with_retry(client, url) for url in cfg.playlist_sources],
            return_exceptions=True,
        )

    failures = [r for r in results if isinstance(r, BaseException)]
    if failures and len(failures) == len(cfg.playlist_sources):
        raise RuntimeError(f"all playlist sources failed: {failures[0]!r}")

    out: list[Channel] = []
    for r in results:
        if isinstance(r, BaseException):
            continue
        out.extend(parse_m3u(r.text))
    return out


def write_raw(channels: list[Channel], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([c.to_dict() for c in channels], indent=2), encoding="utf-8")
