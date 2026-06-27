# Latinos.org

Hispanic/Latino news, celebrity, and culture website serving the US Hispanic community.

## Architecture

### Public Website (deployed to Railway)
- **Stack:** FastAPI + Jinja2 + SQLite (read-only)
- **Sync:** SQLite DB + images pushed via git, auto-deploys to Railway
- **Content:** All content lives in `website/` directory

### Local Admin & Pipeline (self-hosted, NOT deployed)
- **Admin Portal:** FastAPI web UI for reviewing/editing/approving articles
- **Scraper Engine:** RSS feeds + CloakBrowser for inspiration site ingestion
- **LLM Pipeline:** vLLM (qwen3.5-27b) for article rewriting, SEO metadata, quality checks
- **Pipeline:** Scrape → Rewrite → Review → Publish → Git sync to Railway

## Project Structure

```
Latinos/
├── website/          # PUBLIC SITE (deployed to Railway)
│   ├── main.py       # FastAPI application
│   ├── models.py     # SQLAlchemy models
│   ├── routes.py     # Page routes
│   ├── seo.py        # Sitemaps, RSS, meta tags
│   ├── templates/    # Jinja2 templates
│   ├── static/       # CSS, JS, images
│   └── data/         # Synced SQLite DB
├── admin/            # LOCAL ADMIN PORTAL
├── pipeline/         # CONTENT INGESTION ENGINE
├── shared/           # Shared models/config
└── scripts/          # Utility scripts
```

## Setup

### Public Website
```bash
cd website
pip install -r requirements.txt
uvicorn main:app --reload --port 9097
```

### Local Admin Portal
```bash
cd admin
../website/.venv/bin/uvicorn main:app --reload --port 9098
```

Default local admin password: set `ADMIN_PASSWORD`, or use the local-development default.

### Publisher / Railway Sync
```bash
# Publish approved articles, download/optimize images, write manifest
python -m pipeline.publisher

# Commit deployable DB/images/manifest locally
python -m pipeline.publisher --commit

# Commit and push deployable artifacts to GitHub, triggering Railway auto-deploy
python -m pipeline.publisher --push
```

The publisher only stages deployable website artifacts:
`website/data/latinos.db`, `website/data/publish_manifest.json`, and
`website/static/images/articles/`.

### Phase 7 Automation
```bash
# Health/status snapshot (DB counts, source config, optional vLLM check)
python -m pipeline.automation --health --json

# Safe dry-run plan; writes pipeline/runs/latest.json but does not mutate DB/git
python -m pipeline.automation --dry-run --mode rss --auto-approve-min-score 0.85 --json

# Run RSS ingestion, skip LLM, then publish/export locally without pushing
python -m pipeline.automation --run --mode rss --rewrite-limit 0 --publish --json

# Full local automation with limited LLM rewriting and Railway push
python -m pipeline.automation --run --mode rss --rewrite-limit 5 --auto-approve-min-score 0.85 --publish --push
```

The admin dashboard also exposes Phase 7 buttons for status checks, dry-runs,
and a guarded RSS + publisher run. Automation reports are local-only JSON files
under `pipeline/runs/` and are not deployed to Railway.

### Phase 8 Analytics / Growth
```bash
# Generate a read-only analytics report from the shared SQLite DB
python -m pipeline.analytics --days 30 --json

# Save a timestamped local report under pipeline/reports/
python -m pipeline.analytics --days 30 --write --json
```

The admin dashboard exposes `/analytics` and `/analytics/report` for top
articles, category coverage, newsletter signups, share clicks, and growth
recommendations. Public article pages track share clicks and newsletter signup
interest through lightweight local APIs.

## Deployment
Pushes to `main` branch trigger automatic Railway rebuild.

## Content Pipeline
See `pipeline/README.md` for full pipeline documentation.
