from pipeline.dedupe import dedupe_channels
from pipeline.models import Channel


def _ch(name: str, url: str, height: int | None) -> Channel:
    return Channel(
        id="Seven.au", name=name, url=url, logo=None, country="AU",
        categories=["entertainment"], languages=["eng"], resolution_height=height,
        group="Entertainment",
    )


def test_dedupe_keeps_highest_resolution():
    chans = [
        _ch("Seven HD", "https://seven/hd.m3u8", 1080),
        _ch("Seven SD", "https://seven/sd.m3u8", 480),
    ]
    out = dedupe_channels(chans)
    assert len(out) == 1
    assert out[0].resolution_height == 1080


def test_dedupe_prefers_https_when_resolution_equal():
    chans = [
        _ch("Seven", "http://seven/a.m3u8",  720),
        _ch("Seven", "https://seven/b.m3u8", 720),
    ]
    out = dedupe_channels(chans)
    assert out[0].url == "https://seven/b.m3u8"


def test_dedupe_prefers_shorter_url_as_final_tiebreaker():
    chans = [
        _ch("Seven", "https://seven/aaaaa/long-suffix.m3u8", 720),
        _ch("Seven", "https://seven/b.m3u8",                  720),
    ]
    out = dedupe_channels(chans)
    assert out[0].url == "https://seven/b.m3u8"


def test_dedupe_treats_null_height_as_lowest():
    chans = [
        _ch("Seven", "https://seven/a.m3u8", None),
        _ch("Seven", "https://seven/b.m3u8", 480),
    ]
    out = dedupe_channels(chans)
    assert out[0].resolution_height == 480


def test_dedupe_keeps_different_channels_separate():
    chans = [
        Channel(id="ABCNews.au", name="ABC News", url="https://a", logo=None,
                country="AU", categories=["news"], languages=[]),
        Channel(id="Seven.au",   name="Seven",   url="https://b", logo=None,
                country="AU", categories=["entertainment"], languages=[]),
    ]
    out = dedupe_channels(chans)
    assert {c.id for c in out} == {"ABCNews.au", "Seven.au"}


def test_dedupe_groups_by_normalized_name_within_same_channel_id():
    chans = [
        _ch("Seven HD", "https://seven/hd.m3u8", 1080),
        _ch("seven sd", "https://seven/sd.m3u8", 480),
    ]
    out = dedupe_channels(chans)
    assert len(out) == 1
