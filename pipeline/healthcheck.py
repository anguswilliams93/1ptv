from __future__ import annotations

import asyncio
import datetime as dt
import json
from pathlib import Path

import httpx

from pipeline.config import HealthcheckConfig
from pipeline.models import Channel

ALIVE_CONTENT_TYPES: set[str] = {
    "application/vnd.apple.mpegurl",
    "application/x-mpegurl",
    "video/mp2t",
    "video/mp4",
    "application/octet-stream",
}


def load_state(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(path: Path, state: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _ct_alive(content_type: str | None) -> bool:
    if not content_type:
        return False
    ct = content_type.split(";", 1)[0].strip().lower()
    return ct in ALIVE_CONTENT_TYPES


def _should_publish(entry: dict, hc: HealthcheckConfig, protected: bool) -> bool:
    """Whether a probed channel belongs in the output.

    The probe runs from a single (US datacenter) IP, which cannot distinguish a
    genuinely dead stream from one that simply geo/auth-blocks that location — a
    huge share of AU/UK/US broadcast streams answer non-datacenter requests with
    403. So the bar for *dropping* is deliberately high:

    - protected (user-curated) channels are always kept;
    - 'alive' (real stream) and 'reachable' (server answered, e.g. 403 geo-block)
      are kept;
    - only 'dead' endpoints (unreachable host, 404/410, error page) are dropped,
      and even then a grace window absorbs transient blips.
    """
    if protected:
        return True
    if entry.get("last_status") in ("alive", "reachable"):
        return True
    return entry.get("consecutive_failures", 0) < hc.quarantine_threshold


async def _probe_one(client: httpx.AsyncClient, ch: Channel, hc: HealthcheckConfig) -> str:
    """Classify a stream as 'alive', 'reachable', or 'dead'.

    'reachable' means the origin answered but we can't confirm a stream from here
    (geo/auth 403, transient 5xx, redirects) — kept, since it likely plays for an
    in-region viewer. 'dead' is reserved for endpoints that are gone/unroutable.
    """
    headers = {"User-Agent": hc.user_agent}
    try:
        r = await client.head(ch.url, headers=headers, timeout=hc.timeout_seconds)
        if r.status_code in (405, 501) or not r.headers.get("content-type"):
            r = await client.get(
                ch.url,
                headers={**headers, "Range": "bytes=0-1023"},
                timeout=hc.timeout_seconds,
            )
    except (httpx.RequestError, httpx.TimeoutException):
        return "dead"

    code = r.status_code
    if code < 400 and _ct_alive(r.headers.get("content-type")):
        return "alive"
    # Origin responded but isn't a confirmable stream. Auth/geo gates (401/403/
    # 451), method quirks (405/501) and transient server errors (5xx) mean the
    # endpoint is live infrastructure — keep it. A 404/410 or a 2xx error page is
    # genuinely dead.
    if code in (401, 403, 451, 405, 501) or 500 <= code < 600:
        return "reachable"
    return "dead"


async def check_channels(
    channels: list[Channel],
    hc: HealthcheckConfig,
    state_path: Path,
    protected_ids: frozenset[str] | set[str] = frozenset(),
) -> list[Channel]:
    state = load_state(state_path)
    sem = asyncio.Semaphore(hc.concurrency)
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

    async with httpx.AsyncClient(
        follow_redirects=True,
        max_redirects=hc.max_redirects,
        http2=True,
    ) as client:

        async def _one(ch: Channel) -> Channel:
            async with sem:
                status = await _probe_one(client, ch, hc)
            entry = state.get(ch.url, {"consecutive_failures": 0, "last_status": "unknown"})
            if status == "dead":
                entry["consecutive_failures"] = entry.get("consecutive_failures", 0) + 1
            else:  # alive or reachable — the origin answered
                entry["consecutive_failures"] = 0
            entry["last_status"] = status
            ch.status = status
            ch.last_checked = now
            state[ch.url] = entry
            return ch

        probed = await asyncio.gather(*[_one(c) for c in channels])

    save_state(state_path, state)

    return [c for c in probed if _should_publish(state[c.url], hc, c.id in protected_ids)]


def write(channels: list[Channel], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([c.to_dict() for c in channels], indent=2), encoding="utf-8")
