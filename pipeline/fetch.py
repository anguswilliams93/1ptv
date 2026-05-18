from __future__ import annotations

import asyncio
import gzip
import json
from pathlib import Path

import httpx

from pipeline.config import Config
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

        await asyncio.gather(*[_one(code, url) for code, url in cfg.epg_sources.items()])
    return paths


def write_raw(channels: list[Channel], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([c.to_dict() for c in channels], indent=2), encoding="utf-8")
