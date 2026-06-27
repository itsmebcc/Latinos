"""
Pipeline Orchestrator — Manages the full content ingestion cycle.

Two ingestion paths:
  1. RSS feeds (every 15 min): AS USA, Marca, Remezcla, Mitú, Latino Rebels
  2. Browser scraping (every 2 hours): Univision, Telemundo (CloakBrowser)

Both paths insert discovered articles into raw_articles table.
Deduplication is via url_hash (SHA256 of article URL).
"""

import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict

# Add pipeline and website to path
PIPELINE_DIR = Path(__file__).parent
sys.path.insert(0, str(PIPELINE_DIR))
sys.path.insert(0, str(PIPELINE_DIR.parent / "website"))

from config import load_sources
from db import init_db, get_session
from models import Source, RawArticle, PipelineRun, Category
from scraper.rss_scraper import scrape_rss_feed, url_hash
from scraper.web_scraper import scrape_browser_links

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("orchestrator")


def ensure_sources_in_db(config: dict, session) -> Dict[str, dict]:
    """Ensure all configured sources exist in DB. Returns domain->source dict (plain data, no ORM objects)."""
    sources_map = {}
    for src in config.get("sources", []):
        existing = session.query(Source).filter(Source.domain == src["domain"]).first()
        if existing:
            # Update config fields
            existing.name = src["name"]
            existing.site_type = src.get("site_type")
            existing.is_active = src.get("is_active", True)
            source_id = existing.id
        else:
            source = Source(
                name=src["name"],
                domain=src["domain"],
                site_type=src.get("site_type"),
                is_active=src.get("is_active", True),
            )
            session.add(source)
            session.flush()
            source_id = source.id
            logger.info(f"  + Source: {src['name']} ({src['domain']})")

        # Store as plain dict to avoid DetachedInstanceError
        sources_map[src["domain"]] = {
            "id": source_id,
            "name": src["name"],
            "domain": src["domain"],
        }

    session.commit()
    return sources_map


def is_duplicate(session, u_hash: str) -> bool:
    """Check if an article URL hash already exists in DB."""
    return session.query(RawArticle).filter(RawArticle.url_hash == u_hash).first() is not None


def insert_raw_article(session, item: Dict, source: dict) -> bool:
    """Insert a raw article into the DB. Returns True if inserted, False if dup."""
    u_hash = item.get("url_hash") or url_hash(item["url"])

    if is_duplicate(session, u_hash):
        return False

    # Parse publish_date if it's a string
    pub_date = item.get("publish_date")
    if isinstance(pub_date, str):
        from scraper.rss_scraper import parse_date
        pub_date = parse_date(pub_date)

    import json
    image_urls = []
    if item.get("image_url"):
        image_urls.append(item["image_url"])

    raw = RawArticle(
        source_id=source["id"],
        source_url=item["url"],
        url_hash=u_hash,
        title=item.get("title", "")[:500],
        author=item.get("author", ""),
        publish_date=pub_date,
        extracted_text=item.get("body_text", "") or item.get("description", ""),
        image_urls=json.dumps(image_urls),
        category_hint=item.get("category_hint", ""),
        status="discovered",
        discovered_at=item.get("discovered_at", datetime.utcnow()),
    )
    session.add(raw)
    return True


async def run_rss_sources(config: dict, sources_map: dict, max_per_source: int = 30):
    """Scrape all RSS feed sources concurrently."""
    rss_sources = [
        (src, sources_map[src["domain"]])
        for src in config.get("sources", [])
        if src.get("ingestion_method") == "rss" and src.get("is_active")
    ]

    logger.info(f"\n{'='*60}")
    logger.info(f"RSS Scraping Phase — {len(rss_sources)} sources")
    logger.info(f"{'='*60}")

    all_items = []
    for src_cfg, source in rss_sources:
        for feed in src_cfg.get("feeds", []):
            items = await scrape_rss_feed(
                feed_url=feed["url"],
                source_name=source["name"],
                category_hint=feed.get("category_hint", ""),
                max_items=max_per_source,
            )
            all_items.extend([(item, source) for item in items])

    # Insert into DB
    session = get_session()
    inserted = 0
    duplicates = 0
    seen_hashes = set()  # In-batch dedup

    for item, source in all_items:
        u_hash = item.get("url_hash") or url_hash(item["url"])
        if u_hash in seen_hashes:
            duplicates += 1
            continue
        seen_hashes.add(u_hash)
        if insert_raw_article(session, item, source):
            inserted += 1
        else:
            duplicates += 1

    session.commit()
    session.close()

    logger.info(f"\n[RSS] Results: {inserted} new articles, {duplicates} duplicates skipped")
    return inserted, duplicates


async def run_browser_sources(config: dict, sources_map: dict, max_per_source: int = 20):
    """Scrape JS-heavy sites using CloakBrowser."""
    browser_sources = [
        (src, sources_map[src["domain"]])
        for src in config.get("sources", [])
        if src.get("ingestion_method") == "browser" and src.get("is_active")
    ]

    if not browser_sources:
        logger.info("[Browser] No browser-based sources configured")
        return 0, 0

    logger.info(f"\n{'='*60}")
    logger.info(f"Browser Scraping Phase — {len(browser_sources)} sources")
    logger.info(f"{'='*60}")

    all_items = []

    for src_cfg, source in browser_sources:
        for target in src_cfg.get("scrape_targets", []):
            links = await scrape_browser_links(
                target_url=target["url"],
                link_selector=src_cfg.get("link_selector", "article a"),
                source_name=source["name"],
                category_hint=target.get("category_hint", ""),
            )
            # Limit per source
            links = links[:max_per_source]
            all_items.extend([(link, source) for link in links])

    # Insert into DB
    session = get_session()
    inserted = 0
    duplicates = 0
    seen_hashes = set()  # In-batch dedup

    for item, source in all_items:
        u_hash = item.get("url_hash") or url_hash(item.get("url", ""))
        if u_hash in seen_hashes:
            duplicates += 1
            continue
        seen_hashes.add(u_hash)
        # For browser-scraped items, we only have URL + title at this stage.
        item.setdefault("body_text", item.get("title", ""))
        item.setdefault("description", "")
        if insert_raw_article(session, item, source):
            inserted += 1
        else:
            duplicates += 1

    session.commit()
    session.close()

    logger.info(f"\n[Browser] Results: {inserted} new articles, {duplicates} duplicates skipped")
    return inserted, duplicates


async def run_full_cycle():
    """Run a complete scraping cycle (RSS + Browser)."""
    start_time = datetime.utcnow()

    # Initialize
    init_db()
    config = load_sources()
    settings = config.get("settings", {})
    max_per_source = settings.get("max_per_source", 30)

    session = get_session()
    sources_map = ensure_sources_in_db(config, session)
    session.close()

    # Create pipeline run record
    session = get_session()
    run = PipelineRun(
        run_type="full_cycle",
        status="running",
        started_at=start_time,
    )
    session.add(run)
    session.commit()
    run_id = run.id
    session.close()

    logger.info(f"\n🚀 Pipeline Run #{run_id} started at {start_time}")
    logger.info(f"   Active sources: {len([s for s in config['sources'] if s.get('is_active')])}")

    total_inserted = 0
    total_duplicates = 0
    errors = []

    # Phase 1: RSS sources
    try:
        inserted, dups = await run_rss_sources(config, sources_map, max_per_source)
        total_inserted += inserted
        total_duplicates += dups
    except Exception as e:
        logger.error(f"RSS phase failed: {e}")
        errors.append(f"RSS: {e}")

    # Phase 2: Browser sources
    try:
        inserted, dups = await run_browser_sources(config, sources_map, max_per_source)
        total_inserted += inserted
        total_duplicates += dups
    except Exception as e:
        logger.error(f"Browser phase failed: {e}")
        errors.append(f"Browser: {e}")

    # Update pipeline run record
    end_time = datetime.utcnow()
    duration = (end_time - start_time).total_seconds()

    session = get_session()
    run = session.query(PipelineRun).get(run_id)
    run.completed_at = end_time
    run.articles_processed = total_inserted + total_duplicates
    run.articles_succeeded = total_inserted
    run.articles_failed = total_duplicates
    run.status = "completed" if not errors else "completed_with_errors"
    run.error_log = "\n".join(errors) if errors else None
    session.commit()

    # Print summary
    logger.info(f"\n{'='*60}")
    logger.info(f"✅ Pipeline Run #{run_id} Complete")
    logger.info(f"   New articles: {total_inserted}")
    logger.info(f"   Duplicates skipped: {total_duplicates}")
    logger.info(f"   Duration: {duration:.1f}s")
    if errors:
        logger.warning(f"   Errors: {len(errors)}")
    logger.info(f"{'='*60}\n")

    session.close()
    return total_inserted


async def run_rss_only():
    """Run only RSS sources (for frequent 15-min runs)."""
    init_db()
    config = load_sources()
    settings = config.get("settings", {})
    max_per_source = settings.get("max_per_source", 30)

    session = get_session()
    sources_map = ensure_sources_in_db(config, session)
    session.close()

    inserted, dups = await run_rss_sources(config, sources_map, max_per_source)
    return inserted


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Latinos.org Content Pipeline")
    parser.add_argument(
        "--mode",
        choices=["full", "rss", "browser"],
        default="full",
        help="Scraping mode: full (all sources), rss (RSS only), browser (browser only)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't write to DB, just print what would be scraped",
    )

    args = parser.parse_args()

    if args.mode == "full":
        result = asyncio.run(run_full_cycle())
    elif args.mode == "rss":
        result = asyncio.run(run_rss_only())
    else:
        # Browser only
        init_db()
        config = load_sources()
        session = get_session()
        sources_map = ensure_sources_in_db(config, session)
        session.close()
        result = asyncio.run(run_browser_sources(
            config, sources_map,
            config.get("settings", {}).get("max_per_source", 20)
        ))
