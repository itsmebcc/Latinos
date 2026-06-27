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

## Deployment
Pushes to `main` branch trigger automatic Railway rebuild.

## Content Pipeline
See `pipeline/README.md` for full pipeline documentation.
