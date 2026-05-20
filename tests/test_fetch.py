import json
from pathlib import Path

import httpx
import pytest
import respx

from pipeline.config import load_config
from pipeline.fetch import fetch_channels, fetch_epg_files, fetch_playlist_channels


@pytest.mark.asyncio
@respx.mock
async def test_fetch_channels_merges_iptv_org_endpoints(fixtures_dir, tmp_path):
    cfg = load_config(Path("config.yaml"))

    def _body(name: str) -> bytes:
        return (fixtures_dir / name).read_bytes()

    respx.get(cfg.iptv_org["streams"]).mock(return_value=httpx.Response(200, content=_body("streams_sample.json")))
    respx.get(cfg.iptv_org["channels"]).mock(return_value=httpx.Response(200, content=_body("channels_sample.json")))
    respx.get(cfg.iptv_org["categories"]).mock(return_value=httpx.Response(200, content=_body("categories_sample.json")))
    respx.get(cfg.iptv_org["feeds"]).mock(return_value=httpx.Response(200, content=_body("feeds_sample.json")))

    channels = await fetch_channels(cfg)

    by_id = {(c.id, c.url): c for c in channels}
    seven_hd = by_id[("Seven.au", "https://seven.example/hd.m3u8")]
    seven_sd = by_id[("Seven.au", "https://seven.example/sd.m3u8")]
    assert seven_hd.resolution_height == 1080
    assert seven_sd.resolution_height == 480
    assert seven_hd.name == "Seven"

    abcn = by_id[("ABCNews.au", "https://abcnews.example/stream.m3u8")]
    assert abcn.resolution_height == 720
    assert abcn.categories == ["news"]
    assert abcn.logo == "https://logos.example/abcnews.png"
    assert abcn.country == "AU"

    abc1 = by_id[("ABC1.au", "https://abc1.example/stream.m3u8")]
    assert abc1.resolution_height is None


@pytest.mark.asyncio
@respx.mock
async def test_fetch_channels_retries_then_raises(tmp_path):
    cfg = load_config(Path("config.yaml"))
    route = respx.get(cfg.iptv_org["streams"]).mock(return_value=httpx.Response(500))
    respx.get(cfg.iptv_org["channels"]).mock(return_value=httpx.Response(200, content=b"[]"))
    respx.get(cfg.iptv_org["categories"]).mock(return_value=httpx.Response(200, content=b"[]"))
    respx.get(cfg.iptv_org["feeds"]).mock(return_value=httpx.Response(200, content=b"[]"))

    with pytest.raises(httpx.HTTPStatusError):
        await fetch_channels(cfg)
    assert route.call_count == 3


@pytest.mark.asyncio
@respx.mock
async def test_fetch_epg_files_writes_per_country(tmp_path):
    cfg = load_config(Path("config.yaml"))
    sample_xml = b"<?xml version=\"1.0\"?><tv><channel id=\"x\"/></tv>"
    import gzip
    gz = gzip.compress(sample_xml)
    for url in cfg.epg_sources.values():
        respx.get(url).mock(return_value=httpx.Response(200, content=gz))

    out_dir = tmp_path / "epg"
    paths = await fetch_epg_files(cfg, out_dir)

    assert set(paths.keys()) == set(cfg.epg_sources.keys())
    for code, p in paths.items():
        assert p.exists()
        assert p.read_bytes() == sample_xml


@pytest.mark.asyncio
@respx.mock
async def test_fetch_epg_files_partial_failure_keeps_successes(tmp_path):
    cfg = load_config(Path("config.yaml"))
    import gzip
    good = gzip.compress(b"<?xml version=\"1.0\"?><tv/>")
    codes = list(cfg.epg_sources.keys())
    # First half succeeds, second half 500s
    for code in codes[: len(codes) // 2]:
        respx.get(cfg.epg_sources[code]).mock(return_value=httpx.Response(200, content=good))
    for code in codes[len(codes) // 2 :]:
        respx.get(cfg.epg_sources[code]).mock(return_value=httpx.Response(500))

    paths = await fetch_epg_files(cfg, tmp_path / "epg")
    # Only the successes are present, no exception raised.
    assert set(paths.keys()) == set(codes[: len(codes) // 2])


@pytest.mark.asyncio
@respx.mock
async def test_fetch_epg_files_total_failure_raises(tmp_path):
    cfg = load_config(Path("config.yaml"))
    for url in cfg.epg_sources.values():
        respx.get(url).mock(return_value=httpx.Response(500))

    with pytest.raises(RuntimeError, match="all EPG sources failed"):
        await fetch_epg_files(cfg, tmp_path / "epg")


@pytest.mark.asyncio
@respx.mock
async def test_fetch_playlist_channels_downloads_and_parses(fixtures_dir):
    cfg = load_config(Path("config.yaml"))
    body = (fixtures_dir / "freetv_sample.m3u8").read_bytes()
    for url in cfg.playlist_sources:
        respx.get(url).mock(return_value=httpx.Response(200, content=body))

    channels = await fetch_playlist_channels(cfg)
    ids = {c.id for c in channels if c.id}
    assert "BBCOne.uk" in ids
    assert "CBS.us" in ids
    assert len(channels) == 8  # all entries, unfiltered


@pytest.mark.asyncio
@respx.mock
async def test_fetch_playlist_channels_all_fail_raises():
    cfg = load_config(Path("config.yaml"))
    for url in cfg.playlist_sources:
        respx.get(url).mock(return_value=httpx.Response(500))

    with pytest.raises(RuntimeError, match="all playlist sources failed"):
        await fetch_playlist_channels(cfg)


@pytest.mark.asyncio
async def test_fetch_playlist_channels_empty_when_unconfigured():
    cfg = load_config(Path("config.yaml"))
    cfg.playlist_sources = []
    assert await fetch_playlist_channels(cfg) == []
