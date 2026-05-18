import json
from pathlib import Path

import httpx
import pytest
import respx

from pipeline.config import HealthcheckConfig
from pipeline.healthcheck import (
    ALIVE_CONTENT_TYPES,
    check_channels,
    load_state,
    save_state,
)
from pipeline.models import Channel


def _ch(url: str, cid: str = "x.au") -> Channel:
    return Channel(id=cid, name="X", url=url, logo=None, country="AU",
                   categories=[], languages=[])


def _hc(threshold: int = 3) -> HealthcheckConfig:
    return HealthcheckConfig(
        concurrency=10, timeout_seconds=5, max_redirects=3,
        user_agent="VLC/3.0.20 LibVLC/3.0.20",
        quarantine_threshold=threshold,
    )


@pytest.mark.asyncio
@respx.mock
async def test_alive_when_status_ok_and_content_type_matches(tmp_path):
    chans = [_ch("https://alive.example/stream.m3u8")]
    respx.head("https://alive.example/stream.m3u8").mock(
        return_value=httpx.Response(200, headers={"content-type": "application/vnd.apple.mpegurl"})
    )

    state_path = tmp_path / "_state.json"
    result = await check_channels(chans, _hc(), state_path)
    assert len(result) == 1
    assert result[0].status == "alive"


@pytest.mark.asyncio
@respx.mock
async def test_dead_channel_dropped_only_after_threshold(tmp_path):
    url = "https://dead.example/stream.m3u8"
    chans = [_ch(url)]
    respx.head(url).mock(return_value=httpx.Response(500))
    respx.get(url).mock(return_value=httpx.Response(500))

    state_path = tmp_path / "_state.json"
    hc = _hc(threshold=3)

    # 1st failure — still in output (1 < 3)
    r1 = await check_channels(chans, hc, state_path)
    assert len(r1) == 1
    assert r1[0].status == "dead"
    assert load_state(state_path)[url]["consecutive_failures"] == 1

    # 2nd failure — still in output (2 < 3)
    r2 = await check_channels(chans, hc, state_path)
    assert len(r2) == 1
    assert load_state(state_path)[url]["consecutive_failures"] == 2

    # 3rd failure — dropped (3 not < 3)
    r3 = await check_channels(chans, hc, state_path)
    assert r3 == []
    assert load_state(state_path)[url]["consecutive_failures"] == 3


@pytest.mark.asyncio
@respx.mock
async def test_recovery_resets_quarantine_counter(tmp_path):
    url = "https://flap.example/stream.m3u8"
    state_path = tmp_path / "_state.json"
    save_state(state_path, {url: {"consecutive_failures": 5, "last_status": "dead"}})

    respx.head(url).mock(
        return_value=httpx.Response(200, headers={"content-type": "video/mp2t"})
    )

    result = await check_channels([_ch(url)], _hc(), state_path)
    assert len(result) == 1
    s = load_state(state_path)
    assert s[url]["consecutive_failures"] == 0


@pytest.mark.asyncio
@respx.mock
async def test_falls_back_to_get_range_when_head_405(tmp_path):
    url = "https://noheadsupport.example/stream.m3u8"
    respx.head(url).mock(return_value=httpx.Response(405))
    respx.get(url).mock(
        return_value=httpx.Response(206, headers={"content-type": "application/x-mpegurl"})
    )

    result = await check_channels([_ch(url)], _hc(), tmp_path / "_state.json")
    assert len(result) == 1
    assert result[0].status == "alive"


@pytest.mark.asyncio
@respx.mock
async def test_dead_when_content_type_not_video(tmp_path):
    url = "https://html.example/stream.m3u8"
    respx.head(url).mock(
        return_value=httpx.Response(200, headers={"content-type": "text/html"})
    )

    result = await check_channels([_ch(url)], _hc(threshold=1), tmp_path / "_state.json")
    assert result == []


def test_alive_content_types_includes_required_set():
    assert "application/vnd.apple.mpegurl" in ALIVE_CONTENT_TYPES
    assert "application/x-mpegurl" in ALIVE_CONTENT_TYPES
    assert "video/mp2t" in ALIVE_CONTENT_TYPES
    assert "video/mp4" in ALIVE_CONTENT_TYPES
    assert "application/octet-stream" in ALIVE_CONTENT_TYPES
