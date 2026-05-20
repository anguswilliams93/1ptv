import gzip
from pathlib import Path
from xml.etree import ElementTree as ET

from pipeline.config import load_config
from pipeline.emit import emit_epg, emit_playlist
from pipeline.models import Channel


def _ch(**kw) -> Channel:
    defaults = dict(id="ABCNews.au", name="ABC News",
                    url="https://abc/news.m3u8",
                    logo="https://logos/abcnews.png",
                    country="AU", categories=["news"], languages=["eng"],
                    group="AU FTA", status="alive")
    return Channel(**{**defaults, **kw})


def test_playlist_header_contains_url_tvg(tmp_path):
    cfg = load_config(Path("config.yaml"))
    out = tmp_path / "playlist.m3u"
    emit_playlist([_ch()], cfg, out)
    text = out.read_text(encoding="utf-8")
    first = text.splitlines()[0]
    assert first.startswith("#EXTM3U")
    assert cfg.output_epg_url in first


def test_playlist_extinf_includes_tvg_attrs(tmp_path):
    cfg = load_config(Path("config.yaml"))
    out = tmp_path / "playlist.m3u"
    emit_playlist([_ch()], cfg, out)
    text = out.read_text(encoding="utf-8")
    assert 'tvg-id="ABCNews.au"' in text
    assert 'tvg-logo="https://logos/abcnews.png"' in text
    assert 'group-title="AU FTA"' in text
    assert 'tvg-chno="24"' in text
    assert "https://abc/news.m3u8" in text
    assert ",ABC News" in text


def test_playlist_omits_chno_for_non_fta(tmp_path):
    cfg = load_config(Path("config.yaml"))
    out = tmp_path / "playlist.m3u"
    emit_playlist([_ch(id="BBCNews.uk", country="GB", group="News",
                       name="BBC News", url="https://bbc/news.m3u8",
                       logo="https://l/bbc.png")], cfg, out)
    assert "tvg-chno" not in out.read_text(encoding="utf-8")


def test_playlist_orders_by_group(tmp_path):
    cfg = load_config(Path("config.yaml"))
    out = tmp_path / "playlist.m3u"
    chans = [
        _ch(id="News.au", group="News", name="A News", url="https://n"),
        _ch(id="Music.au", group="Music", name="B Music", url="https://m"),
        _ch(id="ABC1.au", group="AU FTA", name="ABC", url="https://a"),
    ]
    emit_playlist(chans, cfg, out)
    text = out.read_text(encoding="utf-8")
    pos_fta   = text.find('group-title="AU FTA"')
    pos_news  = text.find('group-title="News"')
    pos_music = text.find('group-title="Music"')
    assert pos_fta < pos_news < pos_music


def test_playlist_adds_extvlcopt_for_custom_ua_channels(tmp_path):
    cfg = load_config(Path("config.yaml"))
    cfg.custom_user_agent_channels = ["ABCNews.au"]
    out = tmp_path / "playlist.m3u"
    emit_playlist([_ch()], cfg, out)
    text = out.read_text(encoding="utf-8")
    assert "#EXTVLCOPT:http-user-agent=VLC/3.0.20 LibVLC/3.0.20" in text


def test_emit_epg_merges_filters_and_gzips(tmp_path, fixtures_dir):
    cfg = load_config(Path("config.yaml"))
    epg_dir = tmp_path / "epg"
    epg_dir.mkdir()
    (epg_dir / "au.xml").write_bytes((fixtures_dir / "epg_sample_au.xml").read_bytes())
    (epg_dir / "uk.xml").write_bytes((fixtures_dir / "epg_sample_uk.xml").read_bytes())

    kept_channels = [
        _ch(id="ABCNews.au"),
        _ch(id="BBCNews.uk", country="GB", group="News",
            name="BBC News", url="https://bbc/n", logo="https://l/bbc.png"),
    ]
    out = tmp_path / "epg.xml.gz"
    emit_epg(kept_channels, [epg_dir / "au.xml", epg_dir / "uk.xml"], out)

    decompressed = gzip.decompress(out.read_bytes())
    root = ET.fromstring(decompressed)
    ids_in_channels = {c.get("id") for c in root.findall("channel")}
    ids_in_programmes = {p.get("channel") for p in root.findall("programme")}
    assert ids_in_channels == {"ABCNews.au", "BBCNews.uk"}
    assert ids_in_programmes == {"ABCNews.au", "BBCNews.uk"}
    assert "UnusedChannel.au" not in ids_in_channels


def test_emit_epg_applies_id_map(tmp_path):
    """An id_map rewrites upstream EPG ids to the playlist tvg-id so they match."""
    src = tmp_path / "src.xml"
    src.write_text(
        '<?xml version="1.0"?><tv>'
        '<channel id="7HD.au"><display-name>Seven</display-name></channel>'
        '<programme channel="7HD.au" start="20260518040000 +0000" stop="20260518050000 +0000">'
        "<title>News</title></programme>"
        "</tv>",
        encoding="utf-8",
    )
    out = tmp_path / "epg.xml.gz"
    populated = emit_epg([_ch(id="Channel7.au", name="Seven")], [src], out,
                         id_map={"7HD.au": "Channel7.au"})

    root = ET.fromstring(gzip.decompress(out.read_bytes()))
    assert {c.get("id") for c in root.findall("channel")} == {"Channel7.au"}
    assert {p.get("channel") for p in root.findall("programme")} == {"Channel7.au"}
    assert populated == {"Channel7.au"}


def test_emit_epg_returns_only_programme_backed_ids(tmp_path):
    """The returned coverage set counts ids with programmes, not bare <channel> stubs."""
    src = tmp_path / "src.xml"
    src.write_text(
        '<?xml version="1.0"?><tv>'
        '<channel id="ABCNews.au"><display-name>ABC News</display-name></channel>'
        '<channel id="ABCTV.au"><display-name>ABC TV</display-name></channel>'
        '<programme channel="ABCNews.au" start="20260518040000 +0000" stop="20260518050000 +0000">'
        "<title>The World</title></programme>"
        "</tv>",
        encoding="utf-8",
    )
    out = tmp_path / "epg.xml.gz"
    populated = emit_epg([_ch(id="ABCNews.au"), _ch(id="ABCTV.au", name="ABC TV")], [src], out)
    assert populated == {"ABCNews.au"}


def test_emit_epg_dedupes_duplicate_programmes(tmp_path):
    cfg = load_config(Path("config.yaml"))
    epg1 = tmp_path / "a.xml"
    epg2 = tmp_path / "b.xml"
    body = (
        '<?xml version="1.0"?><tv>'
        '<channel id="ABCNews.au"><display-name>ABC News</display-name></channel>'
        '<programme channel="ABCNews.au" start="20260518040000 +0000" stop="20260518050000 +0000">'
        '<title>The World</title></programme>'
        '</tv>'
    )
    epg1.write_text(body, encoding="utf-8")
    epg2.write_text(body, encoding="utf-8")

    out = tmp_path / "epg.xml.gz"
    emit_epg([_ch()], [epg1, epg2], out)
    root = ET.fromstring(gzip.decompress(out.read_bytes()))
    assert len(root.findall("programme")) == 1
    assert len(root.findall("channel")) == 1
