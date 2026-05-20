from scripts.job_summary import render


def test_render_headline_counts_and_drop_rate():
    out = render({"alive": 75, "dead": 25, "epg": {"with_epg": 60, "total": 75}})
    assert "**75 channels published**" in out
    assert "25 dropped as dead" in out
    assert "25% of 100 probed" in out
    assert "EPG coverage:** 60 / 75" in out


def test_render_handles_empty_report():
    out = render({})
    assert "**0 channels published**" in out
    assert "0% of 0 probed" in out  # no division by zero


def test_render_includes_group_table_and_errors():
    out = render({
        "alive": 3, "dead": 0,
        "by_group_alive": {"UK": 2, "USA": 1},
        "errors": ["fetch_playlist_channels: boom"],
    })
    assert "### Published by group" in out
    assert "| UK | 2 |" in out
    assert "### Errors" in out
    assert "`fetch_playlist_channels: boom`" in out


def test_render_embeds_full_json_in_details():
    out = render({"alive": 1, "dead": 0, "raw": 42})
    assert "<details><summary>Full report.json</summary>" in out
    assert '"raw": 42' in out
