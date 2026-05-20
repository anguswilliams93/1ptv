from pathlib import Path

from pipeline.config import load_config
from pipeline.filter import filter_channels, filter_playlist_channels
from pipeline.models import Channel


def _pl(**kw) -> Channel:
    """A channel as produced by the M3U parser: group holds the raw group-title."""
    defaults = dict(id="BBCOne.uk", name="BBC One", url="https://ftv/bbc.m3u8",
                    logo=None, country="GB", categories=[], languages=[], group="UK")
    return Channel(**{**defaults, **kw})


def _ch(**kw) -> Channel:
    defaults = dict(id="x.au", name="X", url="https://x/y.m3u8", logo=None,
                    country="AU", categories=[], languages=[])
    return Channel(**{**defaults, **kw})


def test_filter_keeps_au_channels():
    cfg = load_config(Path("config.yaml"))
    chans = [_ch(id="ABCNews.au", country="AU", categories=["news"], name="ABC News")]
    out = filter_channels(chans, cfg)
    assert len(out) == 1
    assert out[0].group == "AU FTA"


def test_filter_keeps_international_allowlist():
    cfg = load_config(Path("config.yaml"))
    chans = [_ch(id="BBCNews.uk", country="GB", categories=["news"], name="BBC News")]
    out = filter_channels(chans, cfg)
    assert len(out) == 1
    assert out[0].group == "News"


def test_filter_drops_non_au_not_in_allowlist():
    cfg = load_config(Path("config.yaml"))
    chans = [_ch(id="RandomFoo.us", country="US", categories=["news"], name="Random Foo")]
    assert filter_channels(chans, cfg) == []


def test_filter_drops_excluded_category():
    cfg = load_config(Path("config.yaml"))
    chans = [_ch(id="TVSN.au", country="AU", categories=["shop"], name="TVSN")]
    assert filter_channels(chans, cfg) == []


def test_filter_drops_name_pattern():
    cfg = load_config(Path("config.yaml"))
    chans = [
        _ch(id="x.au", country="AU", categories=["news"], name="Test Channel"),
        _ch(id="y.au", country="AU", categories=["music"], name="24/7 Music Loop"),
    ]
    assert filter_channels(chans, cfg) == []


def test_filter_assigns_au_fta_group_overrides_category():
    cfg = load_config(Path("config.yaml"))
    chans = [_ch(id="ABCTV.au", country="AU", categories=["general"], name="ABC TV")]
    out = filter_channels(chans, cfg)
    assert out[0].group == "AU FTA"


def test_filter_assigns_other_for_unmapped_category():
    cfg = load_config(Path("config.yaml"))
    chans = [_ch(id="Weird.au", country="AU", categories=["weather"], name="Weather")]
    out = filter_channels(chans, cfg)
    assert out[0].group == "Other"


def test_filter_uses_first_mapped_category():
    cfg = load_config(Path("config.yaml"))
    chans = [_ch(id="x.au", country="AU", categories=["news", "general"], name="X")]
    assert filter_channels(chans, cfg)[0].group == "News"


def test_playlist_filter_keeps_included_group_and_preserves_country_group():
    cfg = load_config(Path("config.yaml"))
    out = filter_playlist_channels([_pl(group="UK")], cfg)
    assert len(out) == 1
    assert out[0].group == "UK"


def test_playlist_filter_drops_group_not_in_include_list():
    cfg = load_config(Path("config.yaml"))
    assert filter_playlist_channels([_pl(id="RAI1.it", group="Italy", name="RAI 1")], cfg) == []


def test_playlist_filter_remaps_au_fta_ids_to_au_fta_group():
    cfg = load_config(Path("config.yaml"))
    out = filter_playlist_channels([_pl(id="9Gem.au", group="Australia", name="9Gem")], cfg)
    assert out[0].group == "AU FTA"


def test_playlist_filter_drops_name_pattern():
    cfg = load_config(Path("config.yaml"))
    assert filter_playlist_channels([_pl(id="TestUK.uk", group="UK", name="Test Channel")], cfg) == []


def test_playlist_filter_keeps_empty_tvg_id_channel():
    cfg = load_config(Path("config.yaml"))
    out = filter_playlist_channels([_pl(id="", group="UK", name="Local UK")], cfg)
    assert len(out) == 1
    assert out[0].id == ""


def test_playlist_filter_drops_geo_blocked_marker():
    cfg = load_config(Path("config.yaml"))
    chans = [
        _pl(id="BBCOne.uk", group="UK", name="BBC One Ⓖ"),
        _pl(id="E4.uk", group="UK", name="E4 Ⓢ"),
    ]
    out = filter_playlist_channels(chans, cfg)
    assert [c.id for c in out] == ["E4.uk"]  # Ⓖ dropped, Ⓢ kept
