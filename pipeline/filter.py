from __future__ import annotations

import json
from pathlib import Path

from pipeline.config import Config
from pipeline.models import Channel


def _included(ch: Channel, cfg: Config) -> bool:
    if ch.country in cfg.include_countries:
        return True
    return ch.id in cfg.include_channel_ids


def _excluded(ch: Channel, cfg: Config) -> bool:
    if ch.id in cfg.exclude_channel_ids:
        return True
    if any(cat in cfg.exclude_categories for cat in ch.categories):
        return True
    if any(p.search(ch.name) for p in cfg.exclude_name_patterns):
        return True
    return False


def _assign_group(ch: Channel, cfg: Config) -> str:
    if ch.id in cfg.au_fta_ids:
        return "AU FTA"
    for cat in ch.categories:
        if cat in cfg.group_map:
            return cfg.group_map[cat]
    return "Other"


def filter_channels(channels: list[Channel], cfg: Config) -> list[Channel]:
    out: list[Channel] = []
    for ch in channels:
        if not _included(ch, cfg):
            continue
        if _excluded(ch, cfg):
            continue
        ch.group = _assign_group(ch, cfg)
        out.append(ch)
    return out


def write(channels: list[Channel], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([c.to_dict() for c in channels], indent=2), encoding="utf-8")
