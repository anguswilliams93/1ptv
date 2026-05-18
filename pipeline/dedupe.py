from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from pipeline.models import Channel


def _sort_key(ch: Channel) -> tuple:
    height = ch.resolution_height if ch.resolution_height is not None else -1
    https_pref = 1 if ch.url.startswith("https://") else 0
    return (-height, -https_pref, len(ch.url))


def dedupe_channels(channels: list[Channel]) -> list[Channel]:
    buckets: dict[tuple[str, str], list[Channel]] = defaultdict(list)
    for ch in channels:
        buckets[(ch.id, ch.normalized_name())].append(ch)
    out: list[Channel] = []
    for group in buckets.values():
        group.sort(key=_sort_key)
        out.append(group[0])
    return out


def write(channels: list[Channel], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([c.to_dict() for c in channels], indent=2), encoding="utf-8")
