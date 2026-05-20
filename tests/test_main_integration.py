import gzip
import json
from pathlib import Path

import httpx
import pytest
import respx

from pipeline.__main__ import run
from pipeline.config import load_config


@pytest.mark.asyncio
@respx.mock
async def test_full_run_produces_outputs(tmp_path, fixtures_dir, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg_src = Path(__file__).parent.parent / "config.yaml"
    (tmp_path / "config.yaml").write_text(cfg_src.read_text(encoding="utf-8"), encoding="utf-8")

    cfg = load_config(tmp_path / "config.yaml")

    def _body(name: str) -> bytes:
        return (fixtures_dir / name).read_bytes()
    respx.get(cfg.iptv_org["streams"]).mock(return_value=httpx.Response(200, content=_body("streams_sample.json")))
    respx.get(cfg.iptv_org["channels"]).mock(return_value=httpx.Response(200, content=_body("channels_sample.json")))
    respx.get(cfg.iptv_org["categories"]).mock(return_value=httpx.Response(200, content=_body("categories_sample.json")))
    respx.get(cfg.iptv_org["feeds"]).mock(return_value=httpx.Response(200, content=_body("feeds_sample.json")))

    epg_au = (fixtures_dir / "epg_sample_au.xml").read_bytes()
    epg_uk = (fixtures_dir / "epg_sample_uk.xml").read_bytes()
    minimal = b"<?xml version=\"1.0\"?><tv/>"
    respx.get(cfg.epg_sources["AU"]).mock(return_value=httpx.Response(200, content=gzip.compress(epg_au)))
    respx.get(cfg.epg_sources["UK"]).mock(return_value=httpx.Response(200, content=gzip.compress(epg_uk)))
    for code in ("US", "CA", "IE", "QA", "DE", "FR"):
        respx.get(cfg.epg_sources[code]).mock(return_value=httpx.Response(200, content=gzip.compress(minimal)))

    freetv = (fixtures_dir / "freetv_sample.m3u8").read_bytes()
    for s in cfg.playlist_sources:
        body = freetv if "Free-TV" in s.url else b"#EXTM3U\n"
        respx.get(s.url).mock(return_value=httpx.Response(200, content=body))

    for url in [
        "https://abcnews.example/stream.m3u8",
        "https://abc1.example/stream.m3u8",
        "https://seven.example/hd.m3u8",
        "https://seven.example/sd.m3u8",
        "https://bbcnews.example/stream.m3u8",
        # surviving Free-TV streams (Italy + Test are filtered before probing)
        "https://ftv.example/bbcone.m3u8",
        "https://ftv.example/localuk.m3u8",
        "https://ftv.example/cbs.m3u8",
        "https://ftv.example/cbc.m3u8",
        "https://ftv.example/9gem.m3u8",
        "https://ftv.example/ttt.m3u8",
    ]:
        respx.head(url).mock(return_value=httpx.Response(
            200, headers={"content-type": "application/vnd.apple.mpegurl"}
        ))

    await run()

    playlist = (tmp_path / "build" / "out" / "playlist.m3u").read_text(encoding="utf-8")
    assert "#EXTM3U" in playlist
    assert 'tvg-id="ABCNews.au"' in playlist
    assert 'tvg-id="BBCNews.uk"' in playlist
    assert "TVSN.au" not in playlist

    # Free-TV channels merged in under their country groups.
    assert 'tvg-id="BBCOne.uk"' in playlist
    assert 'group-title="UK"' in playlist
    assert 'tvg-id="CBS.us"' in playlist
    assert 'tvg-id="CBCTDT.ca"' in playlist
    # AU free-to-air id from the playlist is remapped to the AU FTA group.
    assert 'tvg-id="9Gem.au" tvg-logo="https://logo/9gem.png" group-title="AU FTA"' in playlist
    # Excluded: group not in include-list, and name matching an exclude pattern.
    assert "RAI1.it" not in playlist
    assert "TestUK.uk" not in playlist

    epg_path = tmp_path / "build" / "out" / "epg.xml.gz"
    assert epg_path.exists()

    report = json.loads((tmp_path / "build" / "report.json").read_text(encoding="utf-8"))
    assert "alive" in report
    assert report["alive"] >= 4
    assert report["raw_playlist"] == 8

    # EPG coverage is reported: ABCNews.au and BBCNews.uk have programmes in the
    # sample sources, so they populate; the rest list without a guide.
    assert report["epg"]["total"] == report["alive"]
    assert report["epg"]["with_epg"] == 2
    assert report["epg"]["with_epg"] < report["epg"]["total"]
    assert "ABCNews.au" not in report["epg"]["missing_ids"]
    assert "Seven.au" in report["epg"]["missing_ids"]


@pytest.mark.asyncio
@respx.mock
async def test_epg_failure_is_non_fatal(tmp_path, fixtures_dir, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg_src = Path(__file__).parent.parent / "config.yaml"
    (tmp_path / "config.yaml").write_text(cfg_src.read_text(encoding="utf-8"), encoding="utf-8")

    cfg = load_config(tmp_path / "config.yaml")

    def _body(name: str) -> bytes:
        return (fixtures_dir / name).read_bytes()
    respx.get(cfg.iptv_org["streams"]).mock(return_value=httpx.Response(200, content=_body("streams_sample.json")))
    respx.get(cfg.iptv_org["channels"]).mock(return_value=httpx.Response(200, content=_body("channels_sample.json")))
    respx.get(cfg.iptv_org["categories"]).mock(return_value=httpx.Response(200, content=_body("categories_sample.json")))
    respx.get(cfg.iptv_org["feeds"]).mock(return_value=httpx.Response(200, content=_body("feeds_sample.json")))

    # All EPG sources fail
    for url in cfg.epg_sources.values():
        respx.get(url).mock(return_value=httpx.Response(500))

    # Playlist sources return no channels (keeps this test focused on EPG).
    for s in cfg.playlist_sources:
        respx.get(s.url).mock(return_value=httpx.Response(200, text="#EXTM3U\n"))

    for url in [
        "https://abcnews.example/stream.m3u8",
        "https://abc1.example/stream.m3u8",
        "https://seven.example/hd.m3u8",
        "https://seven.example/sd.m3u8",
        "https://bbcnews.example/stream.m3u8",
    ]:
        respx.head(url).mock(return_value=httpx.Response(
            200, headers={"content-type": "application/vnd.apple.mpegurl"}
        ))

    # Must not raise
    await run()

    # Playlist still written
    playlist = (tmp_path / "build" / "out" / "playlist.m3u").read_text(encoding="utf-8")
    assert "#EXTM3U" in playlist
    assert 'tvg-id="ABCNews.au"' in playlist

    # EPG file written but empty (no source data merged in)
    assert (tmp_path / "build" / "out" / "epg.xml.gz").exists()

    # Error logged in report
    report = json.loads((tmp_path / "build" / "report.json").read_text(encoding="utf-8"))
    assert any("fetch_epg_files" in e for e in report["errors"])
