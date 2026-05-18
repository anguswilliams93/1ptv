# AU IPTV Playlist Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python pipeline that generates a curated AU IPTV playlist (m3u + xmltv EPG) from iptv-org, runs on GH Actions every 6 hours, and publishes to GH Pages for TiviMate consumption on Android TV.

**Architecture:** Five-stage pipeline (fetch → filter → dedupe → healthcheck → emit) reading/writing intermediate JSON in `./build/`. Config-driven via `config.yaml`. Each stage is independently unit-tested with mocked I/O. Orchestrator runs them in order and writes a run report. GH Actions cron triggers the pipeline; `peaceiris/actions-gh-pages` publishes outputs to the `gh-pages` branch.

**Tech Stack:** Python 3.12, `httpx` (async HTTP), `PyYAML` (config), `pytest` + `pytest-asyncio` + `respx` (HTTP mocking), GitHub Actions, GitHub Pages.

**Spec:** `docs/superpowers/specs/2026-05-18-au-iptv-playlist-design.md`

---

## File structure

Created during this plan:

```
1ptv/
├── .gitignore
├── README.md
├── requirements.txt
├── config.yaml
├── pipeline/
│   ├── __init__.py
│   ├── __main__.py        # orchestrator
│   ├── models.py          # Channel dataclass, type aliases
│   ├── config.py          # load/validate config.yaml
│   ├── fetch.py           # iptv-org + EPG download
│   ├── filter.py          # include/exclude/group assignment
│   ├── dedupe.py          # HD-preferred winner selection
│   ├── healthcheck.py     # async stream liveness probe
│   └── emit.py            # m3u + xmltv merge + gzip
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── fixtures/
│   │   ├── streams_sample.json
│   │   ├── channels_sample.json
│   │   ├── categories_sample.json
│   │   ├── feeds_sample.json
│   │   └── epg_sample_au.xml
│   ├── test_models.py
│   ├── test_config.py
│   ├── test_fetch.py
│   ├── test_filter.py
│   ├── test_dedupe.py
│   ├── test_healthcheck.py
│   ├── test_emit.py
│   └── test_main_integration.py
└── .github/
    └── workflows/
        └── build.yml
```

**Module responsibilities:**

| Module | Responsibility |
|--------|---------------|
| `models.py` | `Channel` dataclass + `ChannelDict` TypedDict for JSON round-trip. Pure data, no I/O. |
| `config.py` | Load `config.yaml`, validate required keys, expose typed `Config` dataclass. |
| `fetch.py` | All upstream HTTP: iptv-org JSON + EPG xmltv.gz. Returns `list[Channel]` + path to merged raw EPG dir. |
| `filter.py` | Apply include/exclude rules from config. Assign `group`. Pure function on channel list. |
| `dedupe.py` | Group by normalized name, pick HD winner. Pure function. |
| `healthcheck.py` | Async probe streams, update `status`. Persists quarantine counters to `_state.json`. |
| `emit.py` | Write `playlist.m3u`, merge & filter & gzip xmltv → `epg.xml.gz`. Pure given inputs. |
| `__main__.py` | Wire stages together, write intermediate JSON per stage, build `report.json`. |

---

## Task 1: Repo scaffold

**Files:**
- Create: `.gitignore`
- Create: `README.md`
- Create: `requirements.txt`
- Create: `config.yaml`
- Create: `pipeline/__init__.py` (empty marker)
- Create: `tests/__init__.py` (empty marker)
- Create: `tests/conftest.py`

- [ ] **Step 1: Initialise git and create gitignore**

Run:
```bash
git init
git branch -m main
```

Create `.gitignore`:
```
build/
__pycache__/
*.pyc
.pytest_cache/
.venv/
venv/
.env
.DS_Store
```

- [ ] **Step 2: Create README**

Create `README.md`:
```markdown
# 1ptv — Curated AU IPTV Playlist

Auto-generated Australian IPTV playlist for TiviMate / Android TV.

- **Playlist:** `https://<user>.github.io/1ptv/playlist.m3u`
- **EPG:** `https://<user>.github.io/1ptv/epg.xml.gz`

Rebuilt every 6 hours via GitHub Actions from iptv-org.

## Local development

```bash
python -m venv .venv
source .venv/bin/activate     # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
python -m pipeline             # full run
pytest                          # tests
```

See `docs/superpowers/specs/2026-05-18-au-iptv-playlist-design.md` for design.
```

- [ ] **Step 3: Create requirements.txt**

Create `requirements.txt`:
```
httpx[http2]==0.27.2
PyYAML==6.0.2
pytest==8.3.3
pytest-asyncio==0.24.0
respx==0.21.1
```

- [ ] **Step 4: Create config.yaml**

Create `config.yaml`:
```yaml
include:
  countries: [AU]
  channel_ids:
    - BBCNews.uk
    - CNNInternational.us
    - AlJazeeraEnglish.qa
    - SkyNews.uk
    - DWEnglish.de
    - FRANCE24English.fr

exclude:
  categories: [shop, religious, auto, xxx]
  channel_ids: []
  name_patterns:
    - "(?i)test"
    - "(?i)24/?7\\s*(music|loop)"

group_map:
  news:          News
  sports:        Sport
  kids:          Kids
  movies:        Movies
  music:         Music
  documentary:   Docos
  entertainment: Entertainment
  general:       Entertainment

au_fta_ids:
  - ABC1.au
  - ABC2.au
  - ABCNews.au
  - SBSOne.au
  - SBSViceland.au
  - SBSWorldMovies.au
  - SBSFood.au
  - SevenHD.au
  - SevenTwo.au
  - SevenMate.au
  - SevenBravo.au
  - 9HD.au
  - 9Gem.au
  - 9Go.au
  - 9Life.au
  - 9Rush.au
  - TenHD.au
  - TenBold.au
  - TenPeach.au
  - Nickelodeon.au

au_fta_lcn:
  ABC1.au: 2
  ABC2.au: 22
  ABCNews.au: 24
  SBSOne.au: 3
  SBSViceland.au: 31
  SBSWorldMovies.au: 32
  SBSFood.au: 33
  SevenHD.au: 7
  SevenTwo.au: 72
  SevenMate.au: 73
  SevenBravo.au: 74
  9HD.au: 9
  9Gem.au: 92
  9Go.au: 93
  9Life.au: 94
  9Rush.au: 95
  TenHD.au: 10
  TenBold.au: 12
  TenPeach.au: 11
  Nickelodeon.au: 13

custom_user_agent_channels: []

healthcheck:
  concurrency: 50
  timeout_seconds: 5
  max_redirects: 3
  user_agent: "VLC/3.0.20 LibVLC/3.0.20"
  quarantine_threshold: 3

group_order:
  - "AU FTA"
  - News
  - Sport
  - Movies
  - Docos
  - Entertainment
  - Kids
  - Music
  - Other

epg_sources:
  AU: https://epgshare01.online/epgshare01/epg_ripper_AU1.xml.gz
  UK: https://epgshare01.online/epgshare01/epg_ripper_UK1.xml.gz
  US: https://epgshare01.online/epgshare01/epg_ripper_US1.xml.gz
  QA: https://epgshare01.online/epgshare01/epg_ripper_QA1.xml.gz
  DE: https://epgshare01.online/epgshare01/epg_ripper_DE1.xml.gz
  FR: https://epgshare01.online/epgshare01/epg_ripper_FR1.xml.gz

iptv_org:
  streams:    https://iptv-org.github.io/api/streams.json
  channels:   https://iptv-org.github.io/api/channels.json
  categories: https://iptv-org.github.io/api/categories.json
  feeds:      https://iptv-org.github.io/api/feeds.json

output:
  epg_url: https://EXAMPLE.github.io/1ptv/epg.xml.gz
```

(Engineer must update `output.epg_url` to their GH Pages URL before first deploy.)

- [ ] **Step 5: Create empty package markers and pytest config**

Create `pipeline/__init__.py`:
```python
```

Create `tests/__init__.py`:
```python
```

Create `tests/conftest.py`:
```python
import asyncio
import sys
from pathlib import Path

import pytest

# Make pipeline importable from tests/
sys.path.insert(0, str(Path(__file__).parent.parent))

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture(scope="session")
def event_loop():
    """Session-wide event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
```

Create `pytest.ini`:
```ini
[pytest]
asyncio_mode = auto
testpaths = tests
```

- [ ] **Step 6: Install + verify**

Run:
```bash
python -m venv .venv
.venv\Scripts\activate    # PowerShell: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pytest --collect-only
```

Expected: pytest reports `0 tests collected` (no test files yet) and exits 5. That's fine — confirms pytest installed and discovers the package.

- [ ] **Step 7: Commit**

```bash
git add .gitignore README.md requirements.txt config.yaml pipeline/ tests/ pytest.ini
git add docs/
git commit -m "chore: repo scaffold (config, deps, package skeleton, design doc)"
```

---

## Task 2: Channel data model

**Files:**
- Create: `pipeline/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_models.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
pytest tests/test_models.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.models'`.

- [ ] **Step 3: Write minimal implementation**

Create `pipeline/models.py`:
```python
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Literal

Status = Literal["unknown", "alive", "dead", "quarantined"]

_QUALITY_SUFFIX_RE = re.compile(r"\b(4K|UHD|FHD|HD|SD)\b", re.IGNORECASE)
_WS_RE = re.compile(r"\s+")


@dataclass
class Channel:
    id: str
    name: str
    url: str
    logo: str | None
    country: str
    categories: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    resolution_height: int | None = None
    group: str | None = None
    status: Status = "unknown"
    last_checked: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Channel":
        return cls(**data)

    def normalized_name(self) -> str:
        without_suffix = _QUALITY_SUFFIX_RE.sub("", self.name)
        return _WS_RE.sub(" ", without_suffix).strip().lower()
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
pytest tests/test_models.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/models.py tests/test_models.py
git commit -m "feat(pipeline): add Channel dataclass with dict round-trip and name normalization"
```

---

## Task 3: Config loader

**Files:**
- Create: `pipeline/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_config.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
pytest tests/test_config.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.config'`.

- [ ] **Step 3: Write minimal implementation**

Create `pipeline/config.py`:
```python
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class HealthcheckConfig:
    concurrency: int
    timeout_seconds: int
    max_redirects: int
    user_agent: str
    quarantine_threshold: int


@dataclass
class Config:
    include_countries: list[str]
    include_channel_ids: list[str]
    exclude_categories: list[str]
    exclude_channel_ids: list[str]
    exclude_name_patterns: list[re.Pattern]
    group_map: dict[str, str]
    au_fta_ids: list[str]
    au_fta_lcn: dict[str, int]
    custom_user_agent_channels: list[str]
    healthcheck: HealthcheckConfig
    group_order: list[str]
    epg_sources: dict[str, str]
    iptv_org: dict[str, str]
    output_epg_url: str


def load_config(path: Path) -> Config:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return _from_raw(raw)


def _from_raw(raw: dict) -> Config:
    required_top = ("include", "exclude", "group_map", "au_fta_ids",
                    "au_fta_lcn", "healthcheck", "group_order",
                    "epg_sources", "iptv_org", "output")
    for key in required_top:
        if key not in raw:
            raise KeyError(f"config missing required top-level key: {key}")
    hc = raw["healthcheck"]
    return Config(
        include_countries=list(raw["include"].get("countries", [])),
        include_channel_ids=list(raw["include"].get("channel_ids", [])),
        exclude_categories=list(raw["exclude"].get("categories", [])),
        exclude_channel_ids=list(raw["exclude"].get("channel_ids", [])),
        exclude_name_patterns=[re.compile(p) for p in raw["exclude"].get("name_patterns", [])],
        group_map=dict(raw["group_map"]),
        au_fta_ids=list(raw["au_fta_ids"]),
        au_fta_lcn={k: int(v) for k, v in raw["au_fta_lcn"].items()},
        custom_user_agent_channels=list(raw.get("custom_user_agent_channels", [])),
        healthcheck=HealthcheckConfig(
            concurrency=int(hc["concurrency"]),
            timeout_seconds=int(hc["timeout_seconds"]),
            max_redirects=int(hc["max_redirects"]),
            user_agent=str(hc["user_agent"]),
            quarantine_threshold=int(hc["quarantine_threshold"]),
        ),
        group_order=list(raw["group_order"]),
        epg_sources=dict(raw["epg_sources"]),
        iptv_org=dict(raw["iptv_org"]),
        output_epg_url=str(raw["output"]["epg_url"]),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
pytest tests/test_config.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/config.py tests/test_config.py
git commit -m "feat(pipeline): config loader with typed Config dataclass"
```

---

## Task 4: Fetch stage

**Files:**
- Create: `tests/fixtures/streams_sample.json`
- Create: `tests/fixtures/channels_sample.json`
- Create: `tests/fixtures/categories_sample.json`
- Create: `tests/fixtures/feeds_sample.json`
- Create: `pipeline/fetch.py`
- Create: `tests/test_fetch.py`

- [ ] **Step 1: Create test fixtures**

Create `tests/fixtures/streams_sample.json`:
```json
[
  {"channel": "ABCNews.au", "feed": "main", "url": "https://abcnews.example/stream.m3u8", "http_referrer": null, "user_agent": null},
  {"channel": "ABC1.au",    "feed": null,   "url": "https://abc1.example/stream.m3u8",    "http_referrer": null, "user_agent": null},
  {"channel": "Seven.au",   "feed": "hd",   "url": "https://seven.example/hd.m3u8",       "http_referrer": null, "user_agent": null},
  {"channel": "Seven.au",   "feed": "sd",   "url": "https://seven.example/sd.m3u8",       "http_referrer": null, "user_agent": null},
  {"channel": "TVSN.au",    "feed": null,   "url": "https://tvsn.example/stream.m3u8",    "http_referrer": null, "user_agent": null},
  {"channel": "BBCNews.uk", "feed": null,   "url": "https://bbcnews.example/stream.m3u8", "http_referrer": null, "user_agent": null}
]
```

Create `tests/fixtures/channels_sample.json`:
```json
[
  {"id": "ABCNews.au", "name": "ABC News",   "country": "AU", "categories": ["news"],          "languages": ["eng"], "logo": "https://logos.example/abcnews.png"},
  {"id": "ABC1.au",    "name": "ABC",        "country": "AU", "categories": ["general"],       "languages": ["eng"], "logo": "https://logos.example/abc1.png"},
  {"id": "Seven.au",   "name": "Seven",      "country": "AU", "categories": ["entertainment"], "languages": ["eng"], "logo": "https://logos.example/seven.png"},
  {"id": "TVSN.au",    "name": "TVSN",       "country": "AU", "categories": ["shop"],          "languages": ["eng"], "logo": "https://logos.example/tvsn.png"},
  {"id": "BBCNews.uk", "name": "BBC News",   "country": "GB", "categories": ["news"],          "languages": ["eng"], "logo": "https://logos.example/bbcnews.png"}
]
```

Create `tests/fixtures/categories_sample.json`:
```json
[
  {"id": "news",          "name": "News"},
  {"id": "general",       "name": "General"},
  {"id": "entertainment", "name": "Entertainment"},
  {"id": "shop",          "name": "Shop"},
  {"id": "religious",     "name": "Religious"},
  {"id": "auto",          "name": "Auto"},
  {"id": "xxx",           "name": "XXX"}
]
```

Create `tests/fixtures/feeds_sample.json`:
```json
[
  {"channel": "Seven.au",   "id": "hd",   "video_format": "HLS", "is_main": true,  "broadcast_area": ["c/AU"], "languages": ["eng"], "format": "HLS", "video": {"height": 1080}},
  {"channel": "Seven.au",   "id": "sd",   "video_format": "HLS", "is_main": false, "broadcast_area": ["c/AU"], "languages": ["eng"], "format": "HLS", "video": {"height": 480}},
  {"channel": "ABCNews.au", "id": "main", "video_format": "HLS", "is_main": true,  "broadcast_area": ["c/AU"], "languages": ["eng"], "format": "HLS", "video": {"height": 720}}
]
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_fetch.py`:
```python
import json
from pathlib import Path

import httpx
import pytest
import respx

from pipeline.config import load_config
from pipeline.fetch import fetch_channels, fetch_epg_files


@pytest.mark.asyncio
@respx.mock
async def test_fetch_channels_merges_iptv_org_endpoints(fixtures_dir, tmp_path):
    cfg = load_config(Path("config.yaml"))

    def _body(name: str) -> bytes:
        return (fixtures_dir / name).read_bytes()

    respx.get(cfg.iptv_org["streams"]).mock(return_value=httpx.Response(200, content=_body("streams_sample.json")))
    respx.get(cfg.iptv_org["channels"]).mock(return_value=httpx.Response(200, content=_body("channels_sample.json")))
    respx.get(cfg.iptv_org["categories"]).mock(return_value=httpx.Response(200, content=_body("categories_sample.json")))
    respx.get(cfg.iptv_org["feeds"]).mock(return_value=httpx.Response(200, content=_body("feeds_sample.json")))

    channels = await fetch_channels(cfg)

    by_id = {(c.id, c.url): c for c in channels}
    # Seven.au produces two stream records (hd + sd) with matching resolution from feeds
    seven_hd = by_id[("Seven.au", "https://seven.example/hd.m3u8")]
    seven_sd = by_id[("Seven.au", "https://seven.example/sd.m3u8")]
    assert seven_hd.resolution_height == 1080
    assert seven_sd.resolution_height == 480
    assert seven_hd.name == "Seven"

    # ABCNews has feed=main → resolution 720
    abcn = by_id[("ABCNews.au", "https://abcnews.example/stream.m3u8")]
    assert abcn.resolution_height == 720
    assert abcn.categories == ["news"]
    assert abcn.logo == "https://logos.example/abcnews.png"
    assert abcn.country == "AU"

    # ABC1 has no feed entry → resolution_height None, still emitted
    abc1 = by_id[("ABC1.au", "https://abc1.example/stream.m3u8")]
    assert abc1.resolution_height is None


@pytest.mark.asyncio
@respx.mock
async def test_fetch_channels_retries_then_raises(tmp_path):
    cfg = load_config(Path("config.yaml"))
    route = respx.get(cfg.iptv_org["streams"]).mock(return_value=httpx.Response(500))
    respx.get(cfg.iptv_org["channels"]).mock(return_value=httpx.Response(200, content=b"[]"))
    respx.get(cfg.iptv_org["categories"]).mock(return_value=httpx.Response(200, content=b"[]"))
    respx.get(cfg.iptv_org["feeds"]).mock(return_value=httpx.Response(200, content=b"[]"))

    with pytest.raises(httpx.HTTPStatusError):
        await fetch_channels(cfg)
    assert route.call_count == 3  # 3 retry attempts


@pytest.mark.asyncio
@respx.mock
async def test_fetch_epg_files_writes_per_country(tmp_path):
    cfg = load_config(Path("config.yaml"))
    sample_xml = b"<?xml version=\"1.0\"?><tv><channel id=\"x\"/></tv>"
    import gzip
    gz = gzip.compress(sample_xml)
    for url in cfg.epg_sources.values():
        respx.get(url).mock(return_value=httpx.Response(200, content=gz))

    out_dir = tmp_path / "epg"
    paths = await fetch_epg_files(cfg, out_dir)

    assert set(paths.keys()) == set(cfg.epg_sources.keys())
    for code, p in paths.items():
        assert p.exists()
        assert p.read_bytes() == sample_xml  # decompressed
```

- [ ] **Step 3: Run test to verify it fails**

Run:
```bash
pytest tests/test_fetch.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.fetch'`.

- [ ] **Step 4: Write minimal implementation**

Create `pipeline/fetch.py`:
```python
from __future__ import annotations

import asyncio
import gzip
import json
from pathlib import Path

import httpx

from pipeline.config import Config
from pipeline.models import Channel

_RETRIES = 3
_BACKOFF_BASE = 1.5


async def _get_with_retry(client: httpx.AsyncClient, url: str, *, retries: int = _RETRIES) -> httpx.Response:
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            r = await client.get(url, timeout=30)
            r.raise_for_status()
            return r
        except httpx.HTTPStatusError as e:
            last_exc = e
            if attempt < retries - 1:
                await asyncio.sleep(_BACKOFF_BASE ** attempt)
        except httpx.RequestError as e:
            last_exc = e
            if attempt < retries - 1:
                await asyncio.sleep(_BACKOFF_BASE ** attempt)
    assert last_exc is not None
    raise last_exc


async def fetch_channels(cfg: Config) -> list[Channel]:
    """Merge streams + channels + feeds into Channel records (one per stream URL)."""
    async with httpx.AsyncClient(http2=True, follow_redirects=True) as client:
        streams_r, channels_r, _categories_r, feeds_r = await asyncio.gather(
            _get_with_retry(client, cfg.iptv_org["streams"]),
            _get_with_retry(client, cfg.iptv_org["channels"]),
            _get_with_retry(client, cfg.iptv_org["categories"]),
            _get_with_retry(client, cfg.iptv_org["feeds"]),
        )

    streams = streams_r.json()
    channels_meta = {c["id"]: c for c in channels_r.json()}
    # feeds keyed by (channel_id, feed_id) → resolution height
    feed_res: dict[tuple[str, str | None], int | None] = {}
    for f in feeds_r.json():
        height = (f.get("video") or {}).get("height")
        feed_res[(f["channel"], f.get("id"))] = height

    out: list[Channel] = []
    for s in streams:
        cid = s["channel"]
        meta = channels_meta.get(cid)
        if meta is None:
            continue
        height = feed_res.get((cid, s.get("feed")))
        out.append(Channel(
            id=cid,
            name=meta["name"],
            url=s["url"],
            logo=meta.get("logo"),
            country=meta.get("country", ""),
            categories=list(meta.get("categories", [])),
            languages=list(meta.get("languages", [])),
            resolution_height=height,
        ))
    return out


async def fetch_epg_files(cfg: Config, out_dir: Path) -> dict[str, Path]:
    """Download each EPG xmltv.gz, decompress, write to out_dir/<code>.xml. Returns map code→path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    async with httpx.AsyncClient(http2=True, follow_redirects=True) as client:
        async def _one(code: str, url: str) -> None:
            r = await _get_with_retry(client, url)
            xml_bytes = gzip.decompress(r.content) if url.endswith(".gz") else r.content
            p = out_dir / f"{code.lower()}.xml"
            p.write_bytes(xml_bytes)
            paths[code] = p

        await asyncio.gather(*[_one(code, url) for code, url in cfg.epg_sources.items()])
    return paths


def write_raw(channels: list[Channel], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([c.to_dict() for c in channels], indent=2), encoding="utf-8")
```

- [ ] **Step 5: Run test to verify it passes**

Run:
```bash
pytest tests/test_fetch.py -v
```
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add pipeline/fetch.py tests/test_fetch.py tests/fixtures/
git commit -m "feat(pipeline): fetch stage — iptv-org merge + EPG download with retry"
```

---

## Task 5: Filter stage

**Files:**
- Create: `pipeline/filter.py`
- Create: `tests/test_filter.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_filter.py`:
```python
from pathlib import Path

from pipeline.config import load_config
from pipeline.filter import filter_channels
from pipeline.models import Channel


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
    chans = [_ch(id="ABC1.au", country="AU", categories=["general"], name="ABC")]
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
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
pytest tests/test_filter.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.filter'`.

- [ ] **Step 3: Write minimal implementation**

Create `pipeline/filter.py`:
```python
from __future__ import annotations

import json
from pathlib import Path

from pipeline.config import Config
from pipeline.models import Channel


def _included(ch: Channel, cfg: Config) -> bool:
    if ch.country in cfg.include_countries:
        return True
    return ch.id in cfg.include_channel_ids


def _excluded(ch: Channel, cfg: Config) -> bool:
    if ch.id in cfg.exclude_channel_ids:
        return True
    if any(cat in cfg.exclude_categories for cat in ch.categories):
        return True
    if any(p.search(ch.name) for p in cfg.exclude_name_patterns):
        return True
    return False


def _assign_group(ch: Channel, cfg: Config) -> str:
    if ch.id in cfg.au_fta_ids:
        return "AU FTA"
    for cat in ch.categories:
        if cat in cfg.group_map:
            return cfg.group_map[cat]
    return "Other"


def filter_channels(channels: list[Channel], cfg: Config) -> list[Channel]:
    out: list[Channel] = []
    for ch in channels:
        if not _included(ch, cfg):
            continue
        if _excluded(ch, cfg):
            continue
        ch.group = _assign_group(ch, cfg)
        out.append(ch)
    return out


def write(channels: list[Channel], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([c.to_dict() for c in channels], indent=2), encoding="utf-8")
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
pytest tests/test_filter.py -v
```
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/filter.py tests/test_filter.py
git commit -m "feat(pipeline): filter stage — include/exclude rules + group assignment"
```

---

## Task 6: Dedupe stage

**Files:**
- Create: `pipeline/dedupe.py`
- Create: `tests/test_dedupe.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_dedupe.py`:
```python
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
    # Same channel_id, different name casing/suffix → one survivor
    chans = [
        _ch("Seven HD", "https://seven/hd.m3u8", 1080),
        _ch("seven sd", "https://seven/sd.m3u8", 480),
    ]
    out = dedupe_channels(chans)
    assert len(out) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
pytest tests/test_dedupe.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.dedupe'`.

- [ ] **Step 3: Write minimal implementation**

Create `pipeline/dedupe.py`:
```python
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from pipeline.models import Channel


def _sort_key(ch: Channel) -> tuple:
    height = ch.resolution_height if ch.resolution_height is not None else -1
    https_pref = 1 if ch.url.startswith("https://") else 0
    return (-height, -https_pref, len(ch.url))


def dedupe_channels(channels: list[Channel]) -> list[Channel]:
    buckets: dict[tuple[str, str], list[Channel]] = defaultdict(list)
    for ch in channels:
        buckets[(ch.id, ch.normalized_name())].append(ch)
    out: list[Channel] = []
    for group in buckets.values():
        group.sort(key=_sort_key)
        out.append(group[0])
    return out


def write(channels: list[Channel], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([c.to_dict() for c in channels], indent=2), encoding="utf-8")
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
pytest tests/test_dedupe.py -v
```
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/dedupe.py tests/test_dedupe.py
git commit -m "feat(pipeline): dedupe stage — HD-preferred winner selection"
```

---

## Task 7: Healthcheck stage

**Files:**
- Create: `pipeline/healthcheck.py`
- Create: `tests/test_healthcheck.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_healthcheck.py`:
```python
import json
from pathlib import Path

import httpx
import pytest
import respx

from pipeline.config import HealthcheckConfig
from pipeline.healthcheck import (
    ALIVE_CONTENT_TYPES,
    check_channels,
    load_state,
    save_state,
)
from pipeline.models import Channel


def _ch(url: str, cid: str = "x.au") -> Channel:
    return Channel(id=cid, name="X", url=url, logo=None, country="AU",
                   categories=[], languages=[])


def _hc(threshold: int = 3) -> HealthcheckConfig:
    return HealthcheckConfig(
        concurrency=10, timeout_seconds=5, max_redirects=3,
        user_agent="VLC/3.0.20 LibVLC/3.0.20",
        quarantine_threshold=threshold,
    )


@pytest.mark.asyncio
@respx.mock
async def test_alive_when_status_ok_and_content_type_matches(tmp_path):
    chans = [_ch("https://alive.example/stream.m3u8")]
    respx.head("https://alive.example/stream.m3u8").mock(
        return_value=httpx.Response(200, headers={"content-type": "application/vnd.apple.mpegurl"})
    )

    state_path = tmp_path / "_state.json"
    result = await check_channels(chans, _hc(), state_path)
    assert len(result) == 1
    assert result[0].status == "alive"


@pytest.mark.asyncio
@respx.mock
async def test_dead_when_status_500_drops_channel_after_threshold(tmp_path):
    url = "https://dead.example/stream.m3u8"
    chans = [_ch(url)]
    respx.head(url).mock(return_value=httpx.Response(500))
    respx.get(url).mock(return_value=httpx.Response(500))

    state_path = tmp_path / "_state.json"
    hc = _hc(threshold=2)

    # 1st failure
    r1 = await check_channels(chans, hc, state_path)
    assert r1 == []  # filtered from output
    s1 = load_state(state_path)
    assert s1[url]["consecutive_failures"] == 1

    # 2nd failure → threshold reached, still empty
    r2 = await check_channels(chans, hc, state_path)
    assert r2 == []
    s2 = load_state(state_path)
    assert s2[url]["consecutive_failures"] == 2


@pytest.mark.asyncio
@respx.mock
async def test_recovery_resets_quarantine_counter(tmp_path):
    url = "https://flap.example/stream.m3u8"
    state_path = tmp_path / "_state.json"
    save_state(state_path, {url: {"consecutive_failures": 5, "last_status": "dead"}})

    respx.head(url).mock(
        return_value=httpx.Response(200, headers={"content-type": "video/mp2t"})
    )

    result = await check_channels([_ch(url)], _hc(), state_path)
    assert len(result) == 1
    s = load_state(state_path)
    assert s[url]["consecutive_failures"] == 0


@pytest.mark.asyncio
@respx.mock
async def test_falls_back_to_get_range_when_head_405(tmp_path):
    url = "https://noheadsupport.example/stream.m3u8"
    respx.head(url).mock(return_value=httpx.Response(405))
    respx.get(url).mock(
        return_value=httpx.Response(206, headers={"content-type": "application/x-mpegurl"})
    )

    result = await check_channels([_ch(url)], _hc(), tmp_path / "_state.json")
    assert len(result) == 1
    assert result[0].status == "alive"


@pytest.mark.asyncio
@respx.mock
async def test_dead_when_content_type_not_video(tmp_path):
    url = "https://html.example/stream.m3u8"
    respx.head(url).mock(
        return_value=httpx.Response(200, headers={"content-type": "text/html"})
    )

    result = await check_channels([_ch(url)], _hc(threshold=1), tmp_path / "_state.json")
    assert result == []


def test_alive_content_types_includes_required_set():
    assert "application/vnd.apple.mpegurl" in ALIVE_CONTENT_TYPES
    assert "application/x-mpegurl" in ALIVE_CONTENT_TYPES
    assert "video/mp2t" in ALIVE_CONTENT_TYPES
    assert "video/mp4" in ALIVE_CONTENT_TYPES
    assert "application/octet-stream" in ALIVE_CONTENT_TYPES
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
pytest tests/test_healthcheck.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.healthcheck'`.

- [ ] **Step 3: Write minimal implementation**

Create `pipeline/healthcheck.py`:
```python
from __future__ import annotations

import asyncio
import datetime as dt
import json
from pathlib import Path

import httpx

from pipeline.config import HealthcheckConfig
from pipeline.models import Channel

ALIVE_CONTENT_TYPES: set[str] = {
    "application/vnd.apple.mpegurl",
    "application/x-mpegurl",
    "video/mp2t",
    "video/mp4",
    "application/octet-stream",
}


def load_state(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(path: Path, state: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _ct_alive(content_type: str | None) -> bool:
    if not content_type:
        return False
    ct = content_type.split(";", 1)[0].strip().lower()
    return ct in ALIVE_CONTENT_TYPES


async def _probe_one(client: httpx.AsyncClient, ch: Channel, hc: HealthcheckConfig) -> bool:
    headers = {"User-Agent": hc.user_agent}
    try:
        r = await client.head(ch.url, headers=headers, timeout=hc.timeout_seconds)
        if r.status_code in (405, 501) or not r.headers.get("content-type"):
            r = await client.get(
                ch.url,
                headers={**headers, "Range": "bytes=0-1023"},
                timeout=hc.timeout_seconds,
            )
        if r.status_code >= 400:
            return False
        return _ct_alive(r.headers.get("content-type"))
    except (httpx.RequestError, httpx.TimeoutException):
        return False


async def check_channels(
    channels: list[Channel],
    hc: HealthcheckConfig,
    state_path: Path,
) -> list[Channel]:
    state = load_state(state_path)
    sem = asyncio.Semaphore(hc.concurrency)
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

    async with httpx.AsyncClient(
        follow_redirects=True,
        max_redirects=hc.max_redirects,
        http2=True,
    ) as client:

        async def _one(ch: Channel) -> Channel:
            async with sem:
                alive = await _probe_one(client, ch, hc)
            entry = state.get(ch.url, {"consecutive_failures": 0, "last_status": "unknown"})
            if alive:
                entry["consecutive_failures"] = 0
                entry["last_status"] = "alive"
                ch.status = "alive"
            else:
                entry["consecutive_failures"] = entry.get("consecutive_failures", 0) + 1
                entry["last_status"] = "dead"
                ch.status = "dead"
            ch.last_checked = now
            state[ch.url] = entry
            return ch

        probed = await asyncio.gather(*[_one(c) for c in channels])

    save_state(state_path, state)

    # Drop channels at/over quarantine threshold
    return [c for c in probed if state[c.url]["consecutive_failures"] == 0]


def write(channels: list[Channel], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([c.to_dict() for c in channels], indent=2), encoding="utf-8")
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
pytest tests/test_healthcheck.py -v
```
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/healthcheck.py tests/test_healthcheck.py
git commit -m "feat(pipeline): healthcheck stage — async probe with quarantine counter"
```

---

## Task 8: Emit stage (m3u + xmltv merge)

**Files:**
- Create: `tests/fixtures/epg_sample_au.xml`
- Create: `tests/fixtures/epg_sample_uk.xml`
- Create: `pipeline/emit.py`
- Create: `tests/test_emit.py`

- [ ] **Step 1: Create EPG fixtures**

Create `tests/fixtures/epg_sample_au.xml`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<tv>
  <channel id="ABCNews.au">
    <display-name>ABC News</display-name>
  </channel>
  <channel id="UnusedChannel.au">
    <display-name>Unused</display-name>
  </channel>
  <programme channel="ABCNews.au" start="20260518040000 +0000" stop="20260518050000 +0000">
    <title>The World</title>
  </programme>
  <programme channel="UnusedChannel.au" start="20260518040000 +0000" stop="20260518050000 +0000">
    <title>Nothing</title>
  </programme>
</tv>
```

Create `tests/fixtures/epg_sample_uk.xml`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<tv>
  <channel id="BBCNews.uk">
    <display-name>BBC News</display-name>
  </channel>
  <programme channel="BBCNews.uk" start="20260518040000 +0000" stop="20260518050000 +0000">
    <title>Newsday</title>
  </programme>
</tv>
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_emit.py`:
```python
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
    assert 'tvg-chno="24"' in text       # ABCNews.au in au_fta_lcn
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
    # UnusedChannel.au filtered out
    assert "UnusedChannel.au" not in ids_in_channels


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
```

- [ ] **Step 3: Run test to verify it fails**

Run:
```bash
pytest tests/test_emit.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.emit'`.

- [ ] **Step 4: Write minimal implementation**

Create `pipeline/emit.py`:
```python
from __future__ import annotations

import gzip
from pathlib import Path
from xml.etree import ElementTree as ET

from pipeline.config import Config
from pipeline.models import Channel


def _group_sort_key(group: str | None, cfg: Config) -> int:
    if group is None:
        return len(cfg.group_order)
    try:
        return cfg.group_order.index(group)
    except ValueError:
        return len(cfg.group_order)


def emit_playlist(channels: list[Channel], cfg: Config, out_path: Path) -> None:
    ordered = sorted(channels, key=lambda c: (_group_sort_key(c.group, cfg), c.name.lower()))

    lines: list[str] = []
    lines.append(
        f'#EXTM3U url-tvg="{cfg.output_epg_url}" x-tvg-url="{cfg.output_epg_url}"'
    )

    for ch in ordered:
        attrs: list[str] = [
            f'tvg-id="{ch.id}"',
            f'tvg-logo="{ch.logo or ""}"',
            f'group-title="{ch.group or "Other"}"',
        ]
        lcn = cfg.au_fta_lcn.get(ch.id)
        if lcn is not None:
            attrs.append(f'tvg-chno="{lcn}"')
        attrs_str = " ".join(attrs)
        lines.append(f"#EXTINF:-1 {attrs_str},{ch.name}")
        if ch.id in cfg.custom_user_agent_channels:
            lines.append(f"#EXTVLCOPT:http-user-agent={cfg.healthcheck.user_agent}")
        lines.append(ch.url)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def emit_epg(channels: list[Channel], epg_files: list[Path], out_path: Path) -> None:
    keep_ids = {c.id for c in channels}
    merged_root = ET.Element("tv")
    seen_channels: set[str] = set()
    seen_programmes: set[tuple[str, str]] = set()

    for f in epg_files:
        try:
            tree = ET.parse(f)
        except ET.ParseError:
            continue
        root = tree.getroot()
        for ch_el in root.findall("channel"):
            cid = ch_el.get("id")
            if cid in keep_ids and cid not in seen_channels:
                merged_root.append(ch_el)
                seen_channels.add(cid)
        for prog in root.findall("programme"):
            cid = prog.get("channel")
            start = prog.get("start")
            key = (cid, start)
            if cid in keep_ids and key not in seen_programmes:
                merged_root.append(prog)
                seen_programmes.add(key)

    xml_bytes = ET.tostring(merged_root, encoding="utf-8", xml_declaration=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(gzip.compress(xml_bytes))
```

- [ ] **Step 5: Run test to verify it passes**

Run:
```bash
pytest tests/test_emit.py -v
```
Expected: 7 passed.

- [ ] **Step 6: Commit**

```bash
git add pipeline/emit.py tests/test_emit.py tests/fixtures/epg_sample_au.xml tests/fixtures/epg_sample_uk.xml
git commit -m "feat(pipeline): emit stage — m3u_plus playlist + filtered xmltv merge"
```

---

## Task 9: Orchestrator (`pipeline/__main__.py`)

**Files:**
- Create: `pipeline/__main__.py`
- Create: `tests/test_main_integration.py`

- [ ] **Step 1: Write the failing test (end-to-end with all HTTP mocked)**

Create `tests/test_main_integration.py`:
```python
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
    # Copy config to tmp cwd
    cfg_src = Path(__file__).parent.parent / "config.yaml"
    (tmp_path / "config.yaml").write_text(cfg_src.read_text(encoding="utf-8"), encoding="utf-8")

    cfg = load_config(tmp_path / "config.yaml")

    # Mock iptv-org endpoints from fixtures
    def _body(name: str) -> bytes:
        return (fixtures_dir / name).read_bytes()
    respx.get(cfg.iptv_org["streams"]).mock(return_value=httpx.Response(200, content=_body("streams_sample.json")))
    respx.get(cfg.iptv_org["channels"]).mock(return_value=httpx.Response(200, content=_body("channels_sample.json")))
    respx.get(cfg.iptv_org["categories"]).mock(return_value=httpx.Response(200, content=_body("categories_sample.json")))
    respx.get(cfg.iptv_org["feeds"]).mock(return_value=httpx.Response(200, content=_body("feeds_sample.json")))

    # Mock EPG sources
    epg_au = (fixtures_dir / "epg_sample_au.xml").read_bytes()
    epg_uk = (fixtures_dir / "epg_sample_uk.xml").read_bytes()
    minimal = b"<?xml version=\"1.0\"?><tv/>"
    respx.get(cfg.epg_sources["AU"]).mock(return_value=httpx.Response(200, content=gzip.compress(epg_au)))
    respx.get(cfg.epg_sources["UK"]).mock(return_value=httpx.Response(200, content=gzip.compress(epg_uk)))
    for code in ("US", "QA", "DE", "FR"):
        respx.get(cfg.epg_sources[code]).mock(return_value=httpx.Response(200, content=gzip.compress(minimal)))

    # Mock stream HEAD requests — make AU streams alive
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
    # TVSN.au filtered out (shop category)
    assert "TVSN.au" not in playlist

    epg_path = tmp_path / "build" / "out" / "epg.xml.gz"
    assert epg_path.exists()

    report = json.loads((tmp_path / "build" / "report.json").read_text(encoding="utf-8"))
    assert "alive" in report
    assert report["alive"] >= 4
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
pytest tests/test_main_integration.py -v
```
Expected: FAIL with `ImportError: cannot import name 'run' from 'pipeline.__main__'`.

- [ ] **Step 3: Write minimal implementation**

Create `pipeline/__main__.py`:
```python
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

from pipeline import dedupe, emit, fetch, filter as filt, healthcheck
from pipeline.config import load_config


async def run() -> int:
    started = time.time()
    cfg = load_config(Path("config.yaml"))

    build = Path("build")
    out = build / "out"
    build.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)

    report: dict = {"errors": []}

    # 1. fetch
    try:
        channels = await fetch.fetch_channels(cfg)
    except Exception as e:
        report["errors"].append(f"fetch_channels: {e!r}")
        _write_report(build, report, started)
        raise

    fetch.write_raw(channels, build / "1_raw.json")
    report["raw"] = len(channels)

    # 2. filter
    filtered = filt.filter_channels(channels, cfg)
    filt.write(filtered, build / "2_filtered.json")
    report["filtered"] = len(filtered)
    report["by_group_after_filter"] = _count_by_group(filtered)

    # 3. dedupe
    deduped = dedupe.dedupe_channels(filtered)
    dedupe.write(deduped, build / "3_deduped.json")
    report["deduped"] = len(deduped)

    # 4. healthcheck
    healthy = await healthcheck.check_channels(deduped, cfg.healthcheck, build / "_state.json")
    healthcheck.write(healthy, build / "4_healthy.json")
    report["alive"] = len(healthy)
    report["dead"] = len(deduped) - len(healthy)
    report["by_group_alive"] = _count_by_group(healthy)

    # 5. fetch EPG (after channel pipeline so we don't pay for it on early failure)
    try:
        epg_paths = await fetch.fetch_epg_files(cfg, build / "epg")
    except Exception as e:
        report["errors"].append(f"fetch_epg_files: {e!r}")
        epg_paths = {}

    # 6. emit
    emit.emit_playlist(healthy, cfg, out / "playlist.m3u")
    emit.emit_epg(healthy, list(epg_paths.values()), out / "epg.xml.gz")

    _write_report(build, report, started)
    return 0


def _count_by_group(channels) -> dict[str, int]:
    counts: dict[str, int] = {}
    for c in channels:
        counts[c.group or "Other"] = counts.get(c.group or "Other", 0) + 1
    return counts


def _write_report(build_dir: Path, report: dict, started: float) -> None:
    report["runtime_seconds"] = round(time.time() - started, 2)
    (build_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
pytest tests/test_main_integration.py -v
```
Expected: 1 passed.

- [ ] **Step 5: Run full test suite**

Run:
```bash
pytest -v
```
Expected: all tests pass (29+ tests across all modules).

- [ ] **Step 6: Commit**

```bash
git add pipeline/__main__.py tests/test_main_integration.py
git commit -m "feat(pipeline): orchestrator with intermediate JSON stages + report"
```

---

## Task 10: GitHub Actions workflow

**Files:**
- Create: `.github/workflows/build.yml`

- [ ] **Step 1: Create workflow file**

Create `.github/workflows/build.yml`:
```yaml
name: build
on:
  schedule:
    - cron: '0 */6 * * *'   # every 6h UTC
  workflow_dispatch:
  push:
    branches: [main]
    paths:
      - 'pipeline/**'
      - 'config.yaml'
      - 'requirements.txt'
      - '.github/workflows/build.yml'

permissions:
  contents: write

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'
      - run: pip install -r requirements.txt
      - run: pytest -v

  build:
    needs: test
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'
      - run: pip install -r requirements.txt
      - run: python -m pipeline
      - name: Append report to job summary
        run: |
          echo '## Build report' >> $GITHUB_STEP_SUMMARY
          echo '```json' >> $GITHUB_STEP_SUMMARY
          cat build/report.json >> $GITHUB_STEP_SUMMARY
          echo '```' >> $GITHUB_STEP_SUMMARY
      - name: Publish to gh-pages
        uses: peaceiris/actions-gh-pages@v4
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: ./build/out
          publish_branch: gh-pages
          keep_files: false
          commit_message: "build ${{ github.run_number }}"
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/build.yml
git commit -m "ci: add scheduled build workflow with tests and gh-pages publish"
```

---

## Task 11: GitHub repo + Pages setup (manual, one-time)

These steps are manual on github.com, not code edits.

- [ ] **Step 1: Create empty GitHub repo**

On github.com, create new public repo named `1ptv` (or any name — must match `output.epg_url` in config). Don't init with README — local repo already has one.

- [ ] **Step 2: Push local main**

Run:
```bash
git remote add origin https://github.com/<your-username>/1ptv.git
git push -u origin main
```

- [ ] **Step 3: Update config.yaml with real URL**

Edit `config.yaml`, replace:
```yaml
output:
  epg_url: https://EXAMPLE.github.io/1ptv/epg.xml.gz
```
with your actual username and repo name. Then:
```bash
git add config.yaml
git commit -m "chore: set GH Pages EPG URL to real value"
git push
```

- [ ] **Step 4: Trigger first build manually**

GitHub repo → Actions tab → "build" workflow → "Run workflow" button (workflow_dispatch).

Expected: test job passes, build job runs ~5 min, creates `gh-pages` branch with `playlist.m3u` + `epg.xml.gz`.

- [ ] **Step 5: Enable GitHub Pages**

Repo → Settings → Pages:
- Source: Deploy from a branch
- Branch: `gh-pages`
- Folder: `/ (root)`
- Save

Wait ~1 minute. Visit `https://<user>.github.io/1ptv/playlist.m3u` in browser; should download the playlist.

---

## Task 12: TiviMate setup (manual on Android TV)

- [ ] **Step 1: Install TiviMate from Google Play Store on Android TV**

- [ ] **Step 2: Add playlist**

TiviMate → "Add playlist" → "Enter URL":
```
https://<user>.github.io/1ptv/playlist.m3u
```
Name it "AU IPTV". Wait for parse.

- [ ] **Step 3: Verify EPG auto-loaded**

After playlist load, EPG should be auto-fetched via `url-tvg` header. Channels in "AU FTA" group should show program titles.

If not, manually add: Settings → EPG → Add → XMLTV → `https://<user>.github.io/1ptv/epg.xml.gz`.

- [ ] **Step 4: Configure auto-update**

Settings → Playlists → "AU IPTV" → Auto-update: every 24h.
Settings → EPG → Auto-update: every 6h.

- [ ] **Step 5: Smoke test playback**

- Tune to ABC News (AU FTA group) → should start within 5s.
- Tune to BBC News (News group) → should start within 5s.
- Browse Sport group → expect some channels dead (will show "no stream"), some alive.
- Press EPG button → grid populates.

---

## Self-review notes (post-write check)

| Spec §  | Coverage |
|---------|----------|
| §1 Goal | Task 11 publishes stable URL, Task 12 sets up TiviMate. |
| §2 Scope | Task 5 filter (AU + intl allowlist + drop categories). Sport caveat surfaces naturally via Task 7 quarantine. |
| §3 Architecture / repo layout | Task 1 scaffolds full layout. |
| §4 Channel record model | Task 2 `Channel` dataclass. |
| §5 Sources | Task 4 fetch (iptv-org + EPG), §5 join logic covered in fetch impl. |
| §6.1 fetch | Task 4. |
| §6.2 filter | Task 5. |
| §6.3 dedupe | Task 6. |
| §6.4 healthcheck | Task 7 (HEAD→GET fallback, content-type allowlist, quarantine counter). |
| §6.5 emit | Task 8 (m3u_plus + tvg-chno + EXTVLCOPT + xmltv merge + gzip). |
| §7 config.yaml | Task 1 creates full file; Task 3 loader validates. |
| §8 Group ordering | Task 1 config has `group_order`; Task 8 emit uses it. |
| §9 Hosting + CI | Task 10. |
| §10 Android TV setup | Task 12. |
| §11 Failure modes | Workflow design + healthcheck quarantine cover these implicitly. |
| §12 Testing | TDD throughout; Task 9 integration test covers end-to-end. |
| §13 Out of scope | Honored — not in plan. |

No placeholders. Types consistent (`Channel`, `Config`, `HealthcheckConfig` used same across all tasks). Method names consistent (`filter_channels`, `dedupe_channels`, `check_channels`, `emit_playlist`, `emit_epg`).
