from pathlib import Path

from pipeline.config import load_config
from pipeline.discover import discover_candidates, render_markdown
from pipeline.models import Channel


def _ch(**kw) -> Channel:
    defaults = dict(
        id="x.us",
        name="X",
        url="https://x/y.m3u8",
        logo=None,
        country="US",
        categories=["news"],
        languages=["eng"],
        resolution_height=720,
    )
    return Channel(**{**defaults, **kw})


def test_discover_suggests_uncovered_english_channel():
    cfg = load_config(Path("config.yaml"))
    channels = [
        # Already covered by include.channel_ids — must not appear.
        _ch(id="BBCNews.uk", name="BBC News", country="GB"),
        # Covered by include.countries AU — must not appear.
        _ch(id="SomeAU.au", name="Some AU", country="AU"),
        # New English news in US — candidate.
        _ch(id="BloombergTV.us", name="Bloomberg TV", country="US", categories=["news"],
            url="https://bloom/hd.m3u8", resolution_height=1080),
        _ch(id="BloombergTV.us", name="Bloomberg TV", country="US", categories=["news"],
            url="https://bloom/sd.m3u8", resolution_height=480),
        # Non-English — skipped when require_english.
        _ch(id="TF1.fr", name="TF1", country="FR", languages=["fra"], categories=["general"]),
        # Excluded category.
        _ch(id="ShopBox.us", name="Shop Box", country="US", categories=["shop"]),
    ]

    found = discover_candidates(channels, cfg)
    ids = [c.id for c in found]
    assert "BloombergTV.us" in ids
    assert "BBCNews.uk" not in ids
    assert "SomeAU.au" not in ids
    assert "TF1.fr" not in ids
    assert "ShopBox.us" not in ids

    bloom = next(c for c in found if c.id == "BloombergTV.us")
    assert bloom.stream_count == 2
    assert bloom.best_height == 1080
    assert bloom.best_url == "https://bloom/hd.m3u8"


def test_discover_respects_max_candidates():
    cfg = load_config(Path("config.yaml"))
    cfg.discovery.max_candidates = 2
    channels = [
        _ch(id=f"Chan{i}.us", name=f"Chan {i}", country="US", categories=["news"])
        for i in range(5)
    ]
    found = discover_candidates(channels, cfg)
    assert len(found) == 2


def test_render_markdown_includes_yaml_snippet():
    cfg = load_config(Path("config.yaml"))
    channels = [_ch(id="FooNews.us", name="Foo News", country="US", categories=["news"])]
    found = discover_candidates(channels, cfg)
    md = render_markdown(found)
    assert "FooNews.us" in md
    assert "include:" in md
    assert "- FooNews.us" in md
