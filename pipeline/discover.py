"""Search iptv-org for English-market channels not yet covered by config.

Usage:
  python -m pipeline.discover
  python -m pipeline.discover --config config.yaml --out build/discover
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from pipeline.config import Config, load_config
from pipeline import fetch
from pipeline.filter import is_excluded
from pipeline.models import Channel


@dataclass
class Candidate:
    id: str
    name: str
    country: str
    categories: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    logo: str | None = None
    stream_count: int = 0
    best_url: str | None = None
    best_height: int | None = None
    reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _already_covered(ch: Channel, cfg: Config) -> bool:
    """True if the channel is already kept by the current build filter rules."""
    if ch.country in cfg.include_countries:
        return True
    if ch.id in cfg.include_channel_ids:
        return True
    if ch.id in cfg.au_fta_ids:
        return True
    return False


def _matches_discovery(ch: Channel, cfg: Config) -> str | None:
    """Return a short reason if this channel is a discovery candidate, else None."""
    disc = cfg.discovery
    if disc.countries and ch.country not in disc.countries:
        return None
    if disc.require_english:
        langs = {lang.lower() for lang in ch.languages}
        if "eng" not in langs and "en" not in langs:
            return None
    if disc.categories and not any(c in disc.categories for c in ch.categories):
        return None
    if is_excluded(ch, cfg):
        return None
    if _already_covered(ch, cfg):
        return None

    reasons: list[str] = []
    if ch.country in disc.countries:
        reasons.append(f"country={ch.country}")
    if any(lang.lower() in ("eng", "en") for lang in ch.languages):
        reasons.append("english")
    if ch.categories:
        reasons.append("cats=" + ",".join(ch.categories[:3]))
    return "; ".join(reasons) if reasons else "match"


def discover_candidates(channels: list[Channel], cfg: Config) -> list[Candidate]:
    """Group raw stream rows by channel id and rank discovery candidates.

    ``channels`` should be the raw iptv-org fetch (one Channel per stream URL).
    """
    by_id: dict[str, list[Channel]] = {}
    for ch in channels:
        by_id.setdefault(ch.id, []).append(ch)

    out: list[Candidate] = []
    for cid, streams in by_id.items():
        sample = streams[0]
        reason = _matches_discovery(sample, cfg)
        if reason is None:
            continue
        best = max(
            streams,
            key=lambda c: (
                c.resolution_height if c.resolution_height is not None else -1,
                1 if c.url.startswith("https://") else 0,
            ),
        )
        out.append(
            Candidate(
                id=cid,
                name=sample.name,
                country=sample.country,
                categories=list(sample.categories),
                languages=list(sample.languages),
                logo=sample.logo,
                stream_count=len(streams),
                best_url=best.url,
                best_height=best.resolution_height,
                reason=reason,
            )
        )

    prefer_cats = {"news", "sports", "documentary", "movies", "entertainment", "kids"}

    def sort_key(c: Candidate) -> tuple:
        cat_score = sum(1 for cat in c.categories if cat in prefer_cats)
        height = c.best_height if c.best_height is not None else -1
        return (-cat_score, -c.stream_count, -height, c.country, c.name.lower())

    out.sort(key=sort_key)
    limit = cfg.discovery.max_candidates
    if limit > 0:
        out = out[:limit]
    return out


def render_markdown(candidates: list[Candidate], *, title: str = "New channel candidates") -> str:
    lines = [
        f"## {title}",
        "",
        f"Found **{len(candidates)}** iptv-org channels with streams that match "
        "discovery rules but are **not** covered by `config.yaml` include rules yet.",
        "",
        "To add one, append its id under `include.channel_ids` (or broaden "
        "`include.countries` if you want a whole market).",
        "",
    ]
    if not candidates:
        lines.append("_No new candidates today._")
        return "\n".join(lines)

    lines += [
        "| id | name | country | categories | streams | height | reason |",
        "|---|---|---|---|---:|---:|---|",
    ]
    for c in candidates:
        cats = ", ".join(c.categories) if c.categories else "—"
        height = c.best_height if c.best_height is not None else "—"
        lines.append(
            f"| `{c.id}` | {c.name} | {c.country} | {cats} | {c.stream_count} | {height} | {c.reason} |"
        )

    lines += [
        "",
        "<details><summary>YAML snippet (copy into config.yaml)</summary>",
        "",
        "```yaml",
        "include:",
        "  channel_ids:",
    ]
    for c in candidates:
        lines.append(f"    - {c.id}  # {c.name} ({c.country})")
    lines += ["```", "", "</details>", ""]
    return "\n".join(lines)


def write_report(candidates: list[Candidate], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([c.to_dict() for c in candidates], indent=2),
        encoding="utf-8",
    )


async def _run(config_path: Path, out_dir: Path) -> int:
    cfg = load_config(config_path)
    out_dir.mkdir(parents=True, exist_ok=True)

    channels = await fetch.fetch_channels(cfg)
    candidates = discover_candidates(channels, cfg)

    write_report(candidates, out_dir / "candidates.json")
    md = render_markdown(candidates)
    (out_dir / "candidates.md").write_text(md, encoding="utf-8")
    print(md)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Discover new IPTV channel candidates")
    p.add_argument("--config", type=Path, default=Path("config.yaml"))
    p.add_argument("--out", type=Path, default=Path("build/discover"))
    args = p.parse_args(argv)
    return asyncio.run(_run(args.config, args.out))


if __name__ == "__main__":
    sys.exit(main())
