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
