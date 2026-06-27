"""
LLM Pipeline Runner — Processes raw_articles through the vLLM rewriting pipeline.

Picks up articles with status='discovered' and runs them through:
  classify → rewrite (ES) → rewrite (EN) → metadata → quality check

Outputs draft articles with status='pending_review' in the articles table.

Usage:
  python -m pipeline.run_llm                    # Process all pending
  python -m pipeline.run_llm --limit 10         # Process max 10
  python -m pipeline.run_llm --concurrency 4    # Limit concurrent requests
  python -m pipeline.run_llm --health           # Check vLLM connectivity
"""

import asyncio
import logging
import sys
import json
from datetime import datetime
from pathlib import Path

# Setup paths
PIPELINE_DIR = Path(__file__).parent
sys.path.insert(0, str(PIPELINE_DIR))
sys.path.insert(0, str(PIPELINE_DIR.parent / "website"))

from config import LLM_CONCURRENCY
from db import init_db, get_session
from models import RawArticle, Article, PipelineRun, Source
from llm.client import check_health
from llm.processor import process_article, save_processed_article

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("llm_runner")


async def run_llm_pipeline(limit: int = 0, concurrency: int = 0):
    """
    Process discovered articles through the LLM pipeline.

    Args:
        limit: Maximum articles to process (0 = all pending)
        concurrency: Max concurrent LLM requests (0 = use config default)
    """
    conc = concurrency or LLM_CONCURRENCY
    start_time = datetime.utcnow()

    # Initialize
    init_db()

    # Check vLLM health
    logger.info("Checking vLLM endpoint...")
    healthy = await check_health()
    if not healthy:
        logger.error("❌ vLLM endpoint not reachable. Make sure vLLM is running.")
        logger.error(f"   Expected at: see VLLM_BASE_URL in pipeline/config.py")
        return 0

    logger.info("✅ vLLM is healthy!")

    # Get pending articles
    session = get_session()
    query = session.query(RawArticle).filter(RawArticle.status == "discovered")
    if limit > 0:
        query = query.limit(limit)

    pending_orm = query.all()

    if not pending_orm:
        logger.info("No pending articles to process.")
        session.close()
        return 0

    # Convert to plain dicts to avoid DetachedInstanceError across sessions
    pending = [{
        "id": art.id,
        "source_id": art.source_id,
        "title": art.title,
        "extracted_text": art.extracted_text,
        "source_url": art.source_url,
        "image_urls": art.image_urls,
        "category_hint": art.category_hint,
    } for art in pending_orm]

    logger.info(f"\n{'='*60}")
    logger.info(f"LLM Pipeline — {len(pending)} articles to process")
    logger.info(f"Concurrency: {conc}")
    logger.info(f"{'='*60}")

    # Create pipeline run record
    run = PipelineRun(
        run_type="llm_rewrite",
        status="running",
        started_at=start_time,
        articles_processed=len(pending),
    )
    session.add(run)
    session.commit()
    run_id = run.id

    # Mark articles as processing
    pending_ids = [p["id"] for p in pending]
    session.query(RawArticle).filter(
        RawArticle.id.in_(pending_ids)
    ).update({"status": "processing", "processed_at": datetime.utcnow()},
    synchronize_session=False)
    session.commit()
    session.close()

    # Process with concurrency control
    semaphore = asyncio.Semaphore(conc)
    results = []
    succeeded = 0
    failed = 0

    async def process_with_semaphore(raw_art):
        async with semaphore:
            return await process_article(raw_art)

    # Create tasks for all articles
    tasks = [process_with_semaphore(art) for art in pending]
    
    # Process and collect results
    for i, coro in enumerate(asyncio.as_completed(tasks)):
        try:
            result = await coro
            if result:
                results.append(result)
                succeeded += 1
                logger.info(f"[{i+1}/{len(pending)}] ✅ Processed (score: {result.get('quality_score', '?')})")
            else:
                failed += 1
                logger.warning(f"[{i+1}/{len(pending)}] ❌ Failed")
        except Exception as e:
            failed += 1
            logger.error(f"[{i+1}/{len(pending)}] ❌ Error: {e}")

    # Save results to DB
    session = get_session()
    saved = 0
    for result in results:
        # Get source name
        source_name = ""
        raw = session.get(RawArticle, result["raw_article_id"])
        if raw:
            source = session.get(Source, raw.source_id)
            if source:
                source_name = source.name

        try:
            article = save_processed_article(session, result, source_name)
            saved += 1

            # Update raw article status
            raw = session.get(RawArticle, result["raw_article_id"])
            if raw:
                raw.status = "rewritten"
        except Exception as e:
            logger.error(f"Error saving article: {e}")
            # Roll back this article
            raw = session.get(RawArticle, result["raw_article_id"])
            if raw:
                raw.status = "discovered"  # Reset for retry

    session.commit()

    # Update failed articles back to discovered
    processed_ids = {r["raw_article_id"] for r in results}
    all_ids = {p["id"] for p in pending}
    failed_ids = all_ids - processed_ids
    if failed_ids:
        session.query(RawArticle).filter(
            RawArticle.id.in_(list(failed_ids))
        ).update({"status": "discovered", "error_message": "LLM processing failed"},
        synchronize_session=False)
        session.commit()

    # Update pipeline run
    end_time = datetime.utcnow()
    duration = (end_time - start_time).total_seconds()
    run = session.query(PipelineRun).get(run_id)
    run.completed_at = end_time
    run.articles_succeeded = saved
    run.articles_failed = failed + (len(pending) - succeeded - failed)
    run.status = "completed"
    session.commit()

    session.close()

    logger.info(f"\n{'='*60}")
    logger.info(f"✅ LLM Pipeline Complete!")
    logger.info(f"   Processed: {succeeded}/{len(pending)}")
    logger.info(f"   Saved: {saved}")
    logger.info(f"   Failed: {failed}")
    logger.info(f"   Duration: {duration:.1f}s ({duration/max(len(pending),1):.1f}s/article)")
    logger.info(f"{'='*60}\n")

    return saved


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Latinos.org LLM Pipeline")
    parser.add_argument("--limit", type=int, default=0, help="Max articles to process")
    parser.add_argument("--concurrency", type=int, default=0, help="Max concurrent requests")
    parser.add_argument("--health", action="store_true", help="Check vLLM health only")

    args = parser.parse_args()

    if args.health:
        asyncio.run(check_health())
    else:
        asyncio.run(run_llm_pipeline(limit=args.limit, concurrency=args.concurrency))
