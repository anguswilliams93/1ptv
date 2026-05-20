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


def _should_publish(entry: dict, hc: HealthcheckConfig) -> bool:
    """Whether a probed channel belongs in the output.

    A channel is published if its latest probe is alive, or if it has a proven
    history of being alive and is still within the transient-failure grace
    window. Channels that have never probed alive (e.g. CDN/geo 403s) are
    dropped immediately rather than shipped while the quarantine counter — which
    resets whenever state isn't persisted between runs — counts up to threshold.
    """
    if entry.get("last_status") == "alive":
        return True
    return bool(entry.get("ever_alive")) and entry.get("consecutive_failures", 0) < hc.quarantine_threshold


async def _probe_one(client: httpx.AsyncClient, ch: Channel, hc: HealthcheckConfig) -> bool:
    headers = {"User-Agent": hc.user_agent}
    try:
        r = await client.head(ch.url, headers=headers, timeout=hc.timeout_seconds)
        if r.status_code in (405, 501) or not r.headers.get("content-type"):
            r = await client.get(
                ch.url,
                headers={**headers, "Range": "bytes=0-1023"},
                timeout=hc.timeout_seconds,
            )
        if r.status_code >= 400:
            return False
        return _ct_alive(r.headers.get("content-type"))
    except (httpx.RequestError, httpx.TimeoutException):
        return False


async def check_channels(
    channels: list[Channel],
    hc: HealthcheckConfig,
    state_path: Path,
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
                alive = await _probe_one(client, ch, hc)
            entry = state.get(
                ch.url,
                {"consecutive_failures": 0, "last_status": "unknown", "ever_alive": False},
            )
            if alive:
                entry["consecutive_failures"] = 0
                entry["last_status"] = "alive"
                entry["ever_alive"] = True
                ch.status = "alive"
            else:
                entry["consecutive_failures"] = entry.get("consecutive_failures", 0) + 1
                entry["last_status"] = "dead"
                ch.status = "dead"
            ch.last_checked = now
            state[ch.url] = entry
            return ch

        probed = await asyncio.gather(*[_one(c) for c in channels])

    save_state(state_path, state)

    return [c for c in probed if _should_publish(state[c.url], hc)]


def write(channels: list[Channel], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([c.to_dict() for c in channels], indent=2), encoding="utf-8")
