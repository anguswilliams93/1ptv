from pipeline.models import Channel


def test_channel_round_trips_through_dict():
    ch = Channel(
        id="ABCNews.au",
        name="ABC News",
        url="https://example.com/abcnews.m3u8",
        logo="https://example.com/abcnews.png",
        country="AU",
        categories=["news"],
        languages=["eng"],
        resolution_height=1080,
        group="News",
        status="alive",
        last_checked="2026-05-18T04:00:00Z",
    )
    as_dict = ch.to_dict()
    restored = Channel.from_dict(as_dict)
    assert restored == ch


def test_channel_defaults():
    ch = Channel(
        id="x.au", name="X", url="https://x/y.m3u8", logo=None,
        country="AU", categories=[], languages=[],
    )
    assert ch.resolution_height is None
    assert ch.group is None
    assert ch.status == "unknown"
    assert ch.last_checked is None


def test_channel_normalized_name_strips_quality_suffixes():
    assert Channel(
        id="x.au", name="ABC News HD", url="u", logo=None,
        country="AU", categories=[], languages=[],
    ).normalized_name() == "abc news"
    assert Channel(
        id="x.au", name="Seven FHD", url="u", logo=None,
        country="AU", categories=[], languages=[],
    ).normalized_name() == "seven"
    assert Channel(
        id="x.au", name="9Gem  SD ", url="u", logo=None,
        country="AU", categories=[], languages=[],
    ).normalized_name() == "9gem"
