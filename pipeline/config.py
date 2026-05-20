from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class HealthcheckConfig:
    concurrency: int
    timeout_seconds: int
    max_redirects: int
    user_agent: str
    quarantine_threshold: int


@dataclass
class Config:
    include_countries: list[str]
    include_channel_ids: list[str]
    exclude_categories: list[str]
    exclude_channel_ids: list[str]
    exclude_name_patterns: list[re.Pattern]
    group_map: dict[str, str]
    au_fta_ids: list[str]
    au_fta_lcn: dict[str, int]
    custom_user_agent_channels: list[str]
    healthcheck: HealthcheckConfig
    group_order: list[str]
    epg_sources: dict[str, str]
    epg_id_map: dict[str, str]
    iptv_org: dict[str, str]
    output_epg_url: str
    playlist_sources: list[str]
    playlist_include_groups: list[str]


def load_config(path: Path) -> Config:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return _from_raw(raw)


def _from_raw(raw: dict) -> Config:
    required_top = ("include", "exclude", "group_map", "au_fta_ids",
                    "au_fta_lcn", "healthcheck", "group_order",
                    "epg_sources", "iptv_org", "output")
    for key in required_top:
        if key not in raw:
            raise KeyError(f"config missing required top-level key: {key}")
    hc = raw["healthcheck"]
    return Config(
        include_countries=list(raw["include"].get("countries", [])),
        include_channel_ids=list(raw["include"].get("channel_ids", [])),
        exclude_categories=list(raw["exclude"].get("categories", [])),
        exclude_channel_ids=list(raw["exclude"].get("channel_ids", [])),
        exclude_name_patterns=[re.compile(p) for p in raw["exclude"].get("name_patterns", [])],
        group_map=dict(raw["group_map"]),
        au_fta_ids=list(raw["au_fta_ids"]),
        au_fta_lcn={k: int(v) for k, v in raw["au_fta_lcn"].items()},
        custom_user_agent_channels=list(raw.get("custom_user_agent_channels", [])),
        healthcheck=HealthcheckConfig(
            concurrency=int(hc["concurrency"]),
            timeout_seconds=int(hc["timeout_seconds"]),
            max_redirects=int(hc["max_redirects"]),
            user_agent=str(hc["user_agent"]),
            quarantine_threshold=int(hc["quarantine_threshold"]),
        ),
        group_order=list(raw["group_order"]),
        epg_sources=dict(raw["epg_sources"]),
        epg_id_map={str(k): str(v) for k, v in (raw.get("epg_id_map") or {}).items()},
        iptv_org=dict(raw["iptv_org"]),
        output_epg_url=str(raw["output"]["epg_url"]),
        playlist_sources=list(raw.get("playlist_sources") or []),
        playlist_include_groups=list(raw.get("playlist_include_groups") or []),
    )
