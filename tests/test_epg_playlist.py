"""EPG ↔ playlist linkage tests.

A channel only shows guide data in a player when its playlist ``tvg-id``
(an iptv-org channel id) matches a ``<channel id>`` / ``<programme channel>``
in the merged xmltv. ``emit_playlist`` and ``emit_epg`` are exercised
elsewhere in isolation; these tests cover the cross-artifact invariant that
governs how many channels actually populate EPG.
"""

import gzip
import re
from pathlib import Path
from xml.etree import ElementTree as ET

from pipeline.config import load_config
from pipeline.emit import emit_epg, emit_playlist
from pipeline.models import Channel

_TVG_ID_RE = re.compile(r'tvg-id="([^"]*)"')


def _ch(**kw) -> Channel:
    defaults = dict(
        id="ABCNews.au", name="ABC News", url="https://abc/news.m3u8",
        logo="https://logos/abcnews.png", country="AU",
        categories=["news"], languages=["eng"], group="AU FTA", status="alive",
    )
    return Channel(**{**defaults, **kw})


def _build_epg(channel_ids, programme_channel_ids=None) -> str:
    """Minimal xmltv document with the given <channel> and <programme> ids."""
    if programme_channel_ids is None:
        programme_channel_ids = channel_ids
    parts = ['<?xml version="1.0" encoding="UTF-8"?>', "<tv>"]
    for cid in channel_ids:
        parts.append(f'<channel id="{cid}"><display-name>{cid}</display-name></channel>')
    for cid in programme_channel_ids:
        parts.append(
            f'<programme channel="{cid}" start="20260518040000 +0000" '
            f'stop="20260518050000 +0000"><title>Show {cid}</title></programme>'
        )
    parts.append("</tv>")
    return "\n".join(parts)


def _write_epg(path: Path, channel_ids, programme_channel_ids=None) -> Path:
    path.write_text(_build_epg(channel_ids, programme_channel_ids), encoding="utf-8")
    return path


def _playlist_tvg_ids(path: Path) -> list[str]:
    return _TVG_ID_RE.findall(path.read_text(encoding="utf-8"))


def _epg_channel_ids(path: Path) -> set:
    root = ET.fromstring(gzip.decompress(path.read_bytes()))
    return {c.get("id") for c in root.findall("channel")}


def _epg_programme_channels(path: Path) -> set:
    root = ET.fromstring(gzip.decompress(path.read_bytes()))
    return {p.get("channel") for p in root.findall("programme")}


def _emit_both(channels, cfg, tmp_path, epg_sources):
    """Emit playlist + EPG from the same channel set; return their paths."""
    playlist = tmp_path / "playlist.m3u"
    epg_out = tmp_path / "epg.xml.gz"
    emit_playlist(channels, cfg, playlist)
    emit_epg(channels, epg_sources, epg_out)
    return playlist, epg_out


def test_playlist_tvg_ids_match_epg_when_ids_align(tmp_path):
    """Full coverage: every playlist tvg-id resolves to programmes in the EPG."""
    cfg = load_config(Path("config.yaml"))
    channels = [
        _ch(id="ABCNews.au"),
        _ch(id="BBCNews.uk", country="GB", group="News", name="BBC News"),
    ]
    src = _write_epg(tmp_path / "src.xml", ["ABCNews.au", "BBCNews.uk"])

    playlist, epg_out = _emit_both(channels, cfg, tmp_path, [src])

    tvg_ids = set(_playlist_tvg_ids(playlist))
    assert tvg_ids == {"ABCNews.au", "BBCNews.uk"}
    assert _epg_programme_channels(epg_out) == tvg_ids
    assert _epg_channel_ids(epg_out) == tvg_ids


def test_epg_only_populates_channels_whose_ids_match_source(tmp_path):
    """The "only N actually populating" symptom.

    Every channel appears in the playlist, but the upstream EPG only carries
    programmes under ids that exactly match the playlist tvg-ids. When the
    source uses a divergent id scheme for the rest (as epgshare01 does versus
    iptv-org), those channels list in the playlist yet stay blank in the guide.
    """
    cfg = load_config(Path("config.yaml"))
    channels = [
        _ch(id="ABCNews.au", name="ABC News"),
        _ch(id="ABCTV.au", name="ABC TV"),
        _ch(id="Channel7.au", name="Seven"),
        _ch(id="Channel9.au", name="Nine"),
        _ch(id="9Gem.au", name="9Gem"),
        _ch(id="9Go.au", name="9Go"),
    ]
    # Source matches only 2 of the 6 playlist ids; the rest use epgshare01-style ids.
    src = _write_epg(
        tmp_path / "src.xml",
        channel_ids=["ABCNews.au", "ABCTV.au", "7HD.au", "9HD.au", "9GEM.au", "9GO.au"],
    )

    playlist, epg_out = _emit_both(channels, cfg, tmp_path, [src])

    tvg_ids = set(_playlist_tvg_ids(playlist))
    populated = _epg_programme_channels(epg_out)

    assert len(tvg_ids) == 6
    assert populated == {"ABCNews.au", "ABCTV.au"}
    assert populated < tvg_ids  # strict subset: most channels have no EPG
    assert populated.isdisjoint({"Channel7.au", "Channel9.au", "9Gem.au", "9Go.au"})


def test_id_map_closes_the_coverage_gap(tmp_path):
    """The fix for "only N populating": mapping the divergent upstream ids onto
    the playlist tvg-ids makes every channel populate."""
    cfg = load_config(Path("config.yaml"))
    channels = [
        _ch(id="ABCNews.au", name="ABC News"),
        _ch(id="Channel7.au", name="Seven"),
        _ch(id="Channel9.au", name="Nine"),
        _ch(id="9Gem.au", name="9Gem"),
    ]
    src = _write_epg(
        tmp_path / "src.xml",
        channel_ids=["ABCNews.au", "7HD.au", "9HD.au", "9GEM.au"],
    )
    id_map = {"7HD.au": "Channel7.au", "9HD.au": "Channel9.au", "9GEM.au": "9Gem.au"}

    playlist = tmp_path / "playlist.m3u"
    epg_out = tmp_path / "epg.xml.gz"
    emit_playlist(channels, cfg, playlist)
    populated = emit_epg(channels, [src], epg_out, id_map=id_map)

    tvg_ids = set(_playlist_tvg_ids(playlist))
    assert populated == tvg_ids  # full coverage after mapping
    assert _epg_programme_channels(epg_out) == tvg_ids
    assert "7HD.au" not in _epg_channel_ids(epg_out)  # rewritten to the tvg-id


def test_epg_is_empty_when_no_playlist_id_matches_source(tmp_path):
    """Worst case: a wholesale id-scheme mismatch yields zero EPG coverage."""
    cfg = load_config(Path("config.yaml"))
    channels = [_ch(id="ABCNews.au"), _ch(id="Channel7.au", name="Seven")]
    src = _write_epg(tmp_path / "src.xml", ["abc-news.au", "seven.au"])

    playlist, epg_out = _emit_both(channels, cfg, tmp_path, [src])

    assert set(_playlist_tvg_ids(playlist)) == {"ABCNews.au", "Channel7.au"}
    assert _epg_channel_ids(epg_out) == set()
    assert _epg_programme_channels(epg_out) == set()


def test_emitted_epg_is_subset_of_playlist_tvg_ids(tmp_path):
    """Invariant: the EPG never carries channels absent from the playlist."""
    cfg = load_config(Path("config.yaml"))
    channels = [_ch(id="ABCNews.au"), _ch(id="BBCNews.uk", country="GB",
                                          group="News", name="BBC News")]
    # Source carries an extra channel that is not in the playlist.
    src = _write_epg(tmp_path / "src.xml", ["ABCNews.au", "BBCNews.uk", "Stranger.au"])

    playlist, epg_out = _emit_both(channels, cfg, tmp_path, [src])

    tvg_ids = set(_playlist_tvg_ids(playlist))
    assert _epg_channel_ids(epg_out) <= tvg_ids
    assert _epg_programme_channels(epg_out) <= tvg_ids
    assert "Stranger.au" not in _epg_channel_ids(epg_out)


def test_programme_populates_even_without_channel_element(tmp_path):
    """A guide entry is kept on id match alone, even if the source omits its
    <channel> element — players bind programmes by the channel attribute."""
    cfg = load_config(Path("config.yaml"))
    channels = [_ch(id="ABCNews.au")]
    src = _write_epg(tmp_path / "src.xml", channel_ids=[],
                     programme_channel_ids=["ABCNews.au"])

    playlist, epg_out = _emit_both(channels, cfg, tmp_path, [src])

    assert "ABCNews.au" in set(_playlist_tvg_ids(playlist))
    assert _epg_channel_ids(epg_out) == set()
    assert _epg_programme_channels(epg_out) == {"ABCNews.au"}


def test_epg_coverage_aggregates_across_multiple_sources(tmp_path):
    """Each playlist channel can draw its EPG from a different country source."""
    cfg = load_config(Path("config.yaml"))
    channels = [
        _ch(id="ABCNews.au"),
        _ch(id="BBCNews.uk", country="GB", group="News", name="BBC News"),
    ]
    au = _write_epg(tmp_path / "au.xml", ["ABCNews.au"])
    uk = _write_epg(tmp_path / "uk.xml", ["BBCNews.uk"])

    playlist, epg_out = _emit_both(channels, cfg, tmp_path, [au, uk])

    assert set(_playlist_tvg_ids(playlist)) == {"ABCNews.au", "BBCNews.uk"}
    assert _epg_programme_channels(epg_out) == {"ABCNews.au", "BBCNews.uk"}


def test_unparsable_source_does_not_break_coverage_from_others(tmp_path):
    """A corrupt EPG file is skipped; channels covered by valid sources still populate."""
    cfg = load_config(Path("config.yaml"))
    channels = [_ch(id="ABCNews.au"), _ch(id="BBCNews.uk", country="GB",
                                          group="News", name="BBC News")]
    good = _write_epg(tmp_path / "good.xml", ["ABCNews.au"])
    bad = tmp_path / "bad.xml"
    bad.write_text("<tv><channel id='BBCNews.uk'></tv>", encoding="utf-8")  # malformed

    playlist, epg_out = _emit_both(channels, cfg, tmp_path, [good, bad])

    assert "ABCNews.au" in set(_playlist_tvg_ids(playlist))
    assert _epg_programme_channels(epg_out) == {"ABCNews.au"}
