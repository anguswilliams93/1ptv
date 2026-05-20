from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

from pipeline import dedupe, emit, fetch, filter as filt, healthcheck
from pipeline.config import load_config


async def run() -> int:
    started = time.time()
    cfg = load_config(Path("config.yaml"))

    build = Path("build")
    out = build / "out"
    build.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)

    report: dict = {"errors": []}

    # iptv-org is fetched best-effort: a transient upstream blip (e.g. GitHub
    # Pages 403/timeout) shouldn't fail the whole build when the external
    # playlist sources can still supply channels.
    channels: list = []
    try:
        channels = await fetch.fetch_channels(cfg)
    except Exception as e:
        report["errors"].append(f"fetch_channels: {e!r}")

    fetch.write_raw(channels, build / "1_raw.json")
    report["raw"] = len(channels)

    playlist_channels: list = []
    try:
        playlist_channels = await fetch.fetch_playlist_channels(cfg)
    except Exception as e:
        report["errors"].append(f"fetch_playlist_channels: {e!r}")
    fetch.write_raw(playlist_channels, build / "1_raw_playlist.json")
    report["raw_playlist"] = len(playlist_channels)

    filtered = filt.filter_channels(channels, cfg) + filt.filter_playlist_channels(
        playlist_channels, cfg
    )
    filt.write(filtered, build / "2_filtered.json")
    report["filtered"] = len(filtered)
    report["by_group_after_filter"] = _count_by_group(filtered)

    deduped = dedupe.dedupe_channels(filtered)
    dedupe.write(deduped, build / "3_deduped.json")
    report["deduped"] = len(deduped)

    # Channels the user explicitly curated are kept regardless of probe result —
    # most are region-locked broadcast streams that 403 from the CI runner's IP
    # but play fine in-region.
    protected = set(cfg.au_fta_ids) | set(cfg.include_channel_ids)
    healthy = await healthcheck.check_channels(
        deduped, cfg.healthcheck, build / "_state.json", protected
    )
    healthcheck.write(healthy, build / "4_healthy.json")
    report["alive"] = len(healthy)
    report["dead"] = len(deduped) - len(healthy)
    report["by_group_alive"] = _count_by_group(healthy)

    try:
        epg_paths = await fetch.fetch_epg_files(cfg, build / "epg")
    except Exception as e:
        report["errors"].append(f"fetch_epg_files: {e!r}")
        epg_paths = {}

    emit.emit_playlist(healthy, cfg, out / "playlist.m3u")
    populated = emit.emit_epg(
        healthy, list(epg_paths.values()), out / "epg.xml.gz", id_map=cfg.epg_id_map
    )
    report["epg"] = {
        "with_epg": len(populated),
        "total": len(healthy),
        "missing_ids": sorted(c.id for c in healthy if c.id not in populated),
    }

    _write_report(build, report, started)
    return 0


def _count_by_group(channels) -> dict[str, int]:
    counts: dict[str, int] = {}
    for c in channels:
        counts[c.group or "Other"] = counts.get(c.group or "Other", 0) + 1
    return counts


def _write_report(build_dir: Path, report: dict, started: float) -> None:
    report["runtime_seconds"] = round(time.time() - started, 2)
    (build_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
