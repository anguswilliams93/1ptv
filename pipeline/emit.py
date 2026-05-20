from __future__ import annotations

import gzip
from pathlib import Path
from xml.etree import ElementTree as ET

from pipeline.config import Config
from pipeline.models import Channel


def _group_sort_key(group: str | None, cfg: Config) -> int:
    if group is None:
        return len(cfg.group_order)
    try:
        return cfg.group_order.index(group)
    except ValueError:
        return len(cfg.group_order)


def emit_playlist(channels: list[Channel], cfg: Config, out_path: Path) -> None:
    ordered = sorted(channels, key=lambda c: (_group_sort_key(c.group, cfg), c.name.lower()))

    lines: list[str] = []
    lines.append(
        f'#EXTM3U url-tvg="{cfg.output_epg_url}" x-tvg-url="{cfg.output_epg_url}"'
    )

    for ch in ordered:
        attrs: list[str] = [
            f'tvg-id="{ch.id}"',
            f'tvg-logo="{ch.logo or ""}"',
            f'group-title="{ch.group or "Other"}"',
        ]
        lcn = cfg.au_fta_lcn.get(ch.id)
        if lcn is not None:
            attrs.append(f'tvg-chno="{lcn}"')
        attrs_str = " ".join(attrs)
        lines.append(f"#EXTINF:-1 {attrs_str},{ch.name}")
        if ch.id in cfg.custom_user_agent_channels:
            lines.append(f"#EXTVLCOPT:http-user-agent={cfg.healthcheck.user_agent}")
        lines.append(ch.url)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))


def emit_epg(
    channels: list[Channel],
    epg_files: list[Path],
    out_path: Path,
    id_map: dict[str, str] | None = None,
) -> set[str]:
    """Merge xmltv sources down to the kept channels, gzip to out_path.

    ``id_map`` rewrites upstream EPG ids (e.g. epgshare01's scheme) to the
    playlist ``tvg-id`` so they match. Returns the set of tvg-ids that ended
    up with at least one programme — i.e. the channels that actually populate
    a guide.
    """
    id_map = id_map or {}
    keep_ids = {c.id for c in channels}
    merged_root = ET.Element("tv")
    seen_channels: set[str] = set()
    seen_programmes: set[tuple[str, str]] = set()
    populated: set[str] = set()

    for f in epg_files:
        try:
            tree = ET.parse(f)
        except ET.ParseError:
            continue
        root = tree.getroot()
        for ch_el in root.findall("channel"):
            cid = id_map.get(ch_el.get("id"), ch_el.get("id"))
            if cid in keep_ids and cid not in seen_channels:
                ch_el.set("id", cid)
                merged_root.append(ch_el)
                seen_channels.add(cid)
        for prog in root.findall("programme"):
            cid = id_map.get(prog.get("channel"), prog.get("channel"))
            start = prog.get("start")
            key = (cid, start)
            if cid in keep_ids and key not in seen_programmes:
                prog.set("channel", cid)
                merged_root.append(prog)
                seen_programmes.add(key)
                populated.add(cid)

    xml_bytes = ET.tostring(merged_root, encoding="utf-8", xml_declaration=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(gzip.compress(xml_bytes))
    return populated
