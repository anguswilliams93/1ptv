"""Render build/report.json as a GitHub Actions step-summary (Markdown).

Usage: python scripts/job_summary.py [report.json]
Prints to stdout; the workflow appends it to $GITHUB_STEP_SUMMARY.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def render(report: dict) -> str:
    alive = report.get("alive", 0)
    dead = report.get("dead", 0)
    probed = alive + dead
    drop_pct = round(dead / probed * 100) if probed else 0
    epg = report.get("epg", {})
    epg_with = epg.get("with_epg", 0)
    epg_total = epg.get("total", 0)

    lines: list[str] = ["## Build report", ""]
    lines.append(
        f"**{alive} channels published** · {dead} dropped as dead "
        f"({drop_pct}% of {probed} probed)"
    )
    lines.append("")
    lines.append(f"**EPG coverage:** {epg_with} / {epg_total} channels have guide data")
    lines.append("")

    lines.append("| stage | channels |")
    lines.append("|---|---:|")
    lines.append(f"| raw (iptv-org) | {report.get('raw', 0)} |")
    lines.append(f"| raw (playlist) | {report.get('raw_playlist', 0)} |")
    lines.append(f"| filtered | {report.get('filtered', 0)} |")
    lines.append(f"| deduped | {report.get('deduped', 0)} |")
    lines.append(f"| alive (published) | {alive} |")
    lines.append(f"| dead (dropped) | {dead} |")

    by_group = report.get("by_group_alive", {})
    if by_group:
        lines += ["", "### Published by group", "", "| group | channels |", "|---|---:|"]
        for group, count in sorted(by_group.items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"| {group} | {count} |")

    errors = report.get("errors", [])
    if errors:
        lines += ["", "### Errors", ""]
        lines += [f"- `{e}`" for e in errors]

    lines += [
        "",
        "<details><summary>Full report.json</summary>",
        "",
        "```json",
        json.dumps(report, indent=2),
        "```",
        "",
        "</details>",
    ]
    return "\n".join(lines)


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "build/report.json")
    report = json.loads(path.read_text(encoding="utf-8"))
    print(render(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
