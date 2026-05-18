# Australian Curated Free IPTV Playlist — Design

**Date:** 2026-05-18
**Status:** Approved, ready for implementation planning
**Owner:** angus

## 1. Goal

Generate a curated, self-healing Australian free IPTV playlist (m3u + xmltv EPG), hosted at a stable URL, consumed by TiviMate on Android TV. Refreshes every 6 hours. Zero ongoing manual maintenance under steady state.

## 2. Scope

**In scope (channels):**
- AU free-to-air + multichannels (ABC, SBS, 7, 9, 10 and digital subs)
- AU 24/7 news (ABC News, Sky AU, 10 News First)
- AU sport (best-effort — high churn, expected partial breakage)
- International FAST channels (BBC, CNN, Al Jazeera, Sky News UK, DW, France 24)

**Out of scope:**
- Paid services (Kayo, Foxtel, Stan, Netflix)
- Pirate movie/series VOD libraries
- DVR / catch-up recording
- Per-device user accounts

**Legal note:** Sport free-stream group is grey-area; included as user-requested with documented expectation that ~50% of streams will be dead at any time due to DMCA churn. Healthcheck hides dead streams automatically. No special handling beyond that.

## 3. Architecture

```
GH Actions cron (every 6h)
        │
        ▼
   pipeline (Python)
   fetch → filter → dedupe → healthcheck → emit
        │
        ▼
   commits playlist.m3u + epg.xml.gz to `gh-pages` branch
        │
        ▼
   https://<user>.github.io/1ptv/playlist.m3u
                            /epg.xml.gz
        │
        ▼
   TiviMate on Android TV (auto-reload playlist 24h, EPG 6h)
```

### Repo layout

```
1ptv/
├── pipeline/
│   ├── __init__.py
│   ├── fetch.py
│   ├── filter.py
│   ├── dedupe.py
│   ├── healthcheck.py
│   ├── emit.py
│   └── __main__.py
├── config.yaml
├── requirements.txt
├── tests/
│   ├── test_filter.py
│   ├── test_dedupe.py
│   ├── test_healthcheck.py
│   └── test_emit.py
├── .github/workflows/build.yml
└── docs/superpowers/specs/2026-05-18-au-iptv-playlist-design.md
```

### Pipeline output layout (per run)

```
build/
├── 1_raw.json          # fetch output
├── 2_filtered.json     # AU + category-passed
├── 3_deduped.json      # HD-preferred
├── 4_healthy.json      # alive streams only
├── _state.json         # quarantine counters (persisted across runs)
├── report.json         # run stats
└── out/
    ├── playlist.m3u
    └── epg.xml.gz
```

## 4. Channel record model

Each channel carried through the pipeline as:

```json
{
  "id": "ABCNews.au",
  "name": "ABC News",
  "url": "https://.../stream.m3u8",
  "logo": "https://.../abcnews.png",
  "country": "AU",
  "categories": ["news"],
  "languages": ["eng"],
  "resolution": { "height": 1080 },
  "group": "News",
  "status": "alive",
  "last_checked": "2026-05-18T04:00:00Z"
}
```

## 5. Sources

### Primary — iptv-org (single upstream)

```
streams:    https://iptv-org.github.io/api/streams.json
channels:   https://iptv-org.github.io/api/channels.json
categories: https://iptv-org.github.io/api/categories.json
feeds:      https://iptv-org.github.io/api/feeds.json
```

### EPG sources

```
AU: https://epgshare01.online/epgshare01/epg_ripper_AU1.xml.gz
UK: https://epgshare01.online/epgshare01/epg_ripper_UK1.xml.gz
US: https://epgshare01.online/epgshare01/epg_ripper_US1.xml.gz
QA: https://epgshare01.online/epgshare01/epg_ripper_QA1.xml.gz
DE: https://epgshare01.online/epgshare01/epg_ripper_DE1.xml.gz
FR: https://epgshare01.online/epgshare01/epg_ripper_FR1.xml.gz
```

Fetch each, concat `<channel>` and `<programme>` elements, dedupe by `(channel, start)`, filter down to ids that survived the pipeline, gzip.

### Join logic

`streams.channel` → `channels.id` (e.g. `ABCNews.au`). EPG xmltv `<channel id="...">` matches same id. No manual mapping required.

## 6. Pipeline stages

### 6.1 fetch (`pipeline/fetch.py`)

- HTTP GET iptv-org JSON endpoints. Retry 3x with exponential backoff.
- Merge streams + channels + categories + feeds into channel records.
- HTTP GET each EPG xmltv.gz, store as `build/_epg_<country>.xml`.
- Write `build/1_raw.json`.

### 6.2 filter (`pipeline/filter.py`)

Config-driven (see §7). Keep channel if:
- `country == "AU"` OR `id in international_allowlist`
- AND no category in `exclude.categories`
- AND `id` not in `exclude.channel_ids`
- AND `name` does not match any `exclude.name_patterns`

Assign `group`:
- If `id in au_fta_ids` → `"AU FTA"`
- Else first category mapped via `group_map`
- Else `"Other"`

Write `build/2_filtered.json`.

### 6.3 dedupe (`pipeline/dedupe.py`)

- Normalize name: lowercase, strip `HD`/`FHD`/`SD`/`4K` suffixes, collapse whitespace.
- Group by `(channel_id, normalized_name)`.
- Winner by sort key: `resolution.height` desc (null = lowest), then `https > http`, then shortest URL length.

Write `build/3_deduped.json`.

### 6.4 healthcheck (`pipeline/healthcheck.py`)

- `httpx.AsyncClient`, concurrency 50, per-request timeout 5s.
- HEAD first; if 405/501 or no content-type, fall back to GET range bytes 0-1024.
- Follow up to 3 redirects.
- Custom UA: `VLC/3.0.20 LibVLC/3.0.20` (default UA gets 403 on some streams).
- Accept if `status < 400` AND `content-type` ∈ `ALIVE_CT`:
  ```python
  ALIVE_CT = {
    "application/vnd.apple.mpegurl",
    "application/x-mpegurl",
    "video/mp2t",
    "video/mp4",
    "application/octet-stream",
  }
  ```
- Persist consecutive-failure count per channel in `build/_state.json`.
- Quarantine rule: drop from output after 3 consecutive failures; restore after 1 success.

Write `build/4_healthy.json` (alive channels only).

### 6.5 emit (`pipeline/emit.py`)

**Playlist** (`build/out/playlist.m3u`) — m3u_plus:
```m3u
#EXTM3U url-tvg="https://<user>.github.io/1ptv/epg.xml.gz" x-tvg-url="https://<user>.github.io/1ptv/epg.xml.gz"
#EXTINF:-1 tvg-id="ABCNews.au" tvg-logo="..." group-title="AU FTA" tvg-chno="24",ABC News
#EXTVLCOPT:http-user-agent=VLC/3.0.20 LibVLC/3.0.20
https://.../abcnews.m3u8
```

- Channels written in group order (§8).
- `tvg-chno` (LCN) emitted only for AU FTA channels, mapped from `au_fta_lcn` config.
- `#EXTVLCOPT:http-user-agent` line added per stream when source flagged as requiring custom UA.

**EPG** (`build/out/epg.xml.gz`):
- Merge source xmltvs.
- Filter `<channel>` and `<programme>` down to `tvg-id`s present in playlist.
- Gzip.

**Report** (`build/report.json`): per-group counts (input, after-filter, after-dedupe, alive, dead, quarantined), upstream errors, total runtime. Appended to GH Action job summary.

## 7. config.yaml

```yaml
include:
  countries: [AU]
  channel_ids:                # international FAST allowlist
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

au_fta_lcn:                   # tvg-chno values for FTA, real LCNs
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

custom_user_agent_channels: []   # ids needing VLC UA, populated as discovered

healthcheck:
  concurrency: 50
  timeout_seconds: 5
  max_redirects: 3
  user_agent: "VLC/3.0.20 LibVLC/3.0.20"
  quarantine_threshold: 3
```

## 8. Group ordering (m3u output)

1. AU FTA
2. News
3. Sport
4. Movies
5. Docos
6. Entertainment
7. Kids
8. Music
9. Other

## 9. Hosting + CI

### `.github/workflows/build.yml`

```yaml
name: build
on:
  schedule:
    - cron: '0 */6 * * *'
  workflow_dispatch:
  push:
    branches: [main]
    paths: [pipeline/**, config.yaml, .github/workflows/build.yml]

permissions:
  contents: write

jobs:
  build:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12', cache: 'pip' }
      - run: pip install -r requirements.txt
      - run: python -m pipeline
      - run: cat build/report.json >> $GITHUB_STEP_SUMMARY
      - uses: peaceiris/actions-gh-pages@v4
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: ./build/out
          publish_branch: gh-pages
          keep_files: false
          commit_message: "build ${{ github.run_number }}"
```

### Stable URLs

```
https://<user>.github.io/1ptv/playlist.m3u
https://<user>.github.io/1ptv/epg.xml.gz
```

Pages enabled via repo Settings → Pages → branch `gh-pages`, path `/`.

## 10. Android TV setup (TiviMate)

1. Install TiviMate from Play Store.
2. Add playlist → M3U Playlist → paste playlist URL above.
3. EPG: auto-loaded via `url-tvg` header in m3u; manual paste also works.
4. Settings → Playlists → Auto-update playlist: 24h. EPG: 6h.
5. Groups appear in sidebar in m3u group-order.

## 11. Failure modes + recovery

| Failure | Behaviour |
|---------|-----------|
| Pipeline crashes | GH Action fails loudly; previous `gh-pages` files remain serving. |
| iptv-org down | fetch retries 3x w/ backoff, then fails the run; nothing published; previous build still live. |
| EPG source down | Skip that country's EPG; run continues; report logs the gap. |
| All channels in a group dead one day | Group omitted from m3u; TiviMate handles fine. |
| GH Pages outage | TiviMate caches last good playlist; TV keeps playing. |

## 12. Testing

Unit tests (pytest) per stage:
- `test_filter.py`: include/exclude/group assignment matrix.
- `test_dedupe.py`: HD>SD, https>http, shortest-URL tiebreakers.
- `test_healthcheck.py`: mocked httpx responses; quarantine counter logic.
- `test_emit.py`: snapshot-test m3u output against golden file; xmltv merge correctness.

No integration tests against live iptv-org (flaky, rate-limit risk). Manual test: `python -m pipeline` locally, verify `build/out/` contents, load `playlist.m3u` in VLC.

## 13. Out of scope / future

- Per-channel quality scoring (sort streams by uptime over rolling window).
- Catchup/timeshift URLs (TiviMate `catchup` attribute) — none of the free AU sources expose them.
- Web dashboard showing live channel health.
- Telegram/email alert on >20% breakage in a run.
- Multiple playlist variants (e.g. kid-safe only).

---

**Implementation plan:** generated separately via writing-plans skill after spec approval.
