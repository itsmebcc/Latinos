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

## Deployment
Pushes to `main` branch trigger automatic Railway rebuild.

## Content Pipeline
See `pipeline/README.md` for full pipeline documentation.
