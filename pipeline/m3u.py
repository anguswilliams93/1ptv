from __future__ import annotations

import re

from pipeline.models import Channel

_ATTR_RE = re.compile(r'([\w-]+)="([^"]*)"')


def _split_extinf(line: str) -> tuple[str, str]:
    """Split an #EXTINF line into (attributes, display-name) at the first
    comma that is not inside a quoted attribute value."""
    body = line[len("#EXTINF:"):]
    in_quotes = False
    for i, ch in enumerate(body):
        if ch == '"':
            in_quotes = not in_quotes
        elif ch == "," and not in_quotes:
            return body[:i], body[i + 1:]
    return body, ""


def parse_m3u(text: str) -> list[Channel]:
    """Parse an extended-M3U playlist into Channel records.

    Each channel is an ``#EXTINF`` line followed by its stream URL; any other
    directive lines (``#EXTVLCOPT``, ``#EXTGRP`` …) between them are skipped.
    The raw ``group-title`` is stored in ``Channel.group`` for downstream
    filtering; entries with no following URL are dropped.
    """
    channels: list[Channel] = []
    lines = text.splitlines()
    i, n = 0, len(lines)
    while i < n:
        line = lines[i].strip()
        if not line.startswith("#EXTINF"):
            i += 1
            continue
        attr_str, title = _split_extinf(line)
        attrs = dict(_ATTR_RE.findall(attr_str))
        j = i + 1
        while j < n and (not lines[j].strip() or lines[j].lstrip().startswith("#")):
            j += 1
        if j >= n:
            break
        name = title.strip() or attrs.get("tvg-name", "").strip()
        channels.append(Channel(
            id=attrs.get("tvg-id", ""),
            name=name,
            url=lines[j].strip(),
            logo=attrs.get("tvg-logo") or None,
            country=attrs.get("tvg-country", ""),
            group=attrs.get("group-title") or None,
        ))
        i = j + 1
    return channels
