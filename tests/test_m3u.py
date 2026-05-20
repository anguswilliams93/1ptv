from pipeline.m3u import parse_m3u


def test_parse_basic_channel(fixtures_dir):
    text = (fixtures_dir / "freetv_sample.m3u8").read_text(encoding="utf-8")
    channels = parse_m3u(text)
    by_id = {c.id: c for c in channels if c.id}

    bbc = by_id["BBCOne.uk"]
    assert bbc.name == "BBC One"
    assert bbc.url == "https://ftv.example/bbcone.m3u8"
    assert bbc.logo == "https://logo/bbcone.png"
    assert bbc.country == "GB"
    assert bbc.group == "UK"
    assert bbc.categories == []
    assert bbc.resolution_height is None


def test_parse_keeps_empty_tvg_id_and_blank_logo(fixtures_dir):
    text = (fixtures_dir / "freetv_sample.m3u8").read_text(encoding="utf-8")
    local = next(c for c in parse_m3u(text) if c.name == "Local UK")
    assert local.id == ""
    assert local.logo is None  # blank tvg-logo normalizes to None
    assert local.url == "https://ftv.example/localuk.m3u8"


def test_parse_pairs_every_extinf_with_a_url(fixtures_dir):
    text = (fixtures_dir / "freetv_sample.m3u8").read_text(encoding="utf-8")
    channels = parse_m3u(text)
    assert len(channels) == 8
    assert all(c.url.startswith("https://") for c in channels)


def test_parse_display_name_with_comma_and_attr_commas():
    text = (
        "#EXTM3U\n"
        '#EXTINF:-1 tvg-id="X.us" group-title="News, Live",Channel One, HD\n'
        "https://x.example/one.m3u8\n"
    )
    [ch] = parse_m3u(text)
    assert ch.group == "News, Live"
    assert ch.name == "Channel One, HD"
    assert ch.id == "X.us"


def test_parse_skips_intermediate_directive_lines():
    text = (
        "#EXTM3U\n"
        '#EXTINF:-1 tvg-id="Y.uk" group-title="UK",Y\n'
        "#EXTVLCOPT:http-user-agent=Mozilla\n"
        "#EXTGRP:UK\n"
        "https://y.example/y.m3u8\n"
    )
    [ch] = parse_m3u(text)
    assert ch.url == "https://y.example/y.m3u8"
    assert ch.id == "Y.uk"


def test_parse_drops_trailing_extinf_without_url():
    text = (
        "#EXTM3U\n"
        '#EXTINF:-1 tvg-id="A.uk" group-title="UK",A\n'
        "https://a.example/a.m3u8\n"
        '#EXTINF:-1 tvg-id="B.uk" group-title="UK",B\n'
    )
    channels = parse_m3u(text)
    assert [c.id for c in channels] == ["A.uk"]


def test_parse_empty_input_returns_empty():
    assert parse_m3u("") == []
    assert parse_m3u("#EXTM3U\n") == []
