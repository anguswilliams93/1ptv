from pathlib import Path

import pytest

from pipeline.config import Config, load_config


def test_load_config_from_project_root():
    cfg = load_config(Path("config.yaml"))
    assert isinstance(cfg, Config)
    assert "AU" in cfg.include_countries
    assert "shop" in cfg.exclude_categories
    assert cfg.group_map["news"] == "News"
    assert "ABCNews.au" in cfg.au_fta_ids
    assert cfg.au_fta_lcn["ABCNews.au"] == 24
    assert cfg.healthcheck.concurrency == 50
    assert cfg.healthcheck.quarantine_threshold == 3
    assert cfg.group_order[0] == "AU FTA"
    assert cfg.epg_sources["AU"].startswith("https://")
    assert cfg.iptv_org["streams"].endswith("streams.json")
    assert cfg.output_epg_url.startswith("https://")
    assert cfg.epg_id_map == {}


def test_epg_id_map_parses_string_pairs(tmp_path):
    src = Path("config.yaml").read_text(encoding="utf-8")
    src = src.replace("epg_id_map: {}", "epg_id_map:\n  7HD.au: Channel7.au")
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(src, encoding="utf-8")
    cfg = load_config(cfg_path)
    assert cfg.epg_id_map == {"7HD.au": "Channel7.au"}


def test_load_config_rejects_missing_required_key(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("include:\n  countries: [AU]\n", encoding="utf-8")
    with pytest.raises(KeyError):
        load_config(bad)


def test_compiled_exclude_patterns(tmp_path):
    cfg = load_config(Path("config.yaml"))
    assert any(p.search("Test Channel") for p in cfg.exclude_name_patterns)
    assert any(p.search("24/7 Music Loop") for p in cfg.exclude_name_patterns)
    assert not any(p.search("ABC News") for p in cfg.exclude_name_patterns)
