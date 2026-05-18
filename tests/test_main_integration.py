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
    for code in ("US", "QA", "DE", "FR"):
        respx.get(cfg.epg_sources[code]).mock(return_value=httpx.Response(200, content=gzip.compress(minimal)))

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

    await run()

    playlist = (tmp_path / "build" / "out" / "playlist.m3u").read_text(encoding="utf-8")
    assert "#EXTM3U" in playlist
    assert 'tvg-id="ABCNews.au"' in playlist
    assert 'tvg-id="BBCNews.uk"' in playlist
    assert "TVSN.au" not in playlist

    epg_path = tmp_path / "build" / "out" / "epg.xml.gz"
    assert epg_path.exists()

    report = json.loads((tmp_path / "build" / "report.json").read_text(encoding="utf-8"))
    assert "alive" in report
    assert report["alive"] >= 4
