# 1ptv — Free English IPTV Playlist

English-language free IPTV channels, **health-tested and deployed every day** via GitHub Actions.

- **Playlist:** `https://anguswilliams93.github.io/1ptv/playlist.m3u`
- **EPG (guide):** `https://anguswilliams93.github.io/1ptv/epg.xml.gz`

Channels are pulled from public sources, filtered to English-language markets (Australia, UK, USA, Canada, Ireland, Trinidad), de-duplicated, and probed for reachability before publishing. The guide data (EPG) is merged and shipped alongside.

## Add it to your IPTV app

Most M3U-based IPTV players let you add a remote playlist by URL. The exact wording varies by app, but the steps are the same:

1. Open your IPTV app and go to **Add playlist** (sometimes **Add source** / **Add provider**).
2. Choose **Add via URL** (rather than a local file) and paste the **Playlist** URL above.
3. When asked for an **EPG / XMLTV URL**, paste the **EPG** URL above so you get the channel guide.
4. Save and let the app load. Refresh the playlist anytime to pick up the daily rebuild.

The EPG URL is also embedded in the playlist header, so apps that read it automatically will find the guide without a separate entry.

## Local development

```bash
python -m venv .venv
source .venv/bin/activate     # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
python -m pipeline             # full run
pytest                          # tests
```

See `docs/superpowers/specs/2026-05-18-au-iptv-playlist-design.md` for design.
