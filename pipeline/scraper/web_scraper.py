"""
CloakBrowser Web Scraper — Python wrapper for the Node.js bridge.
Used for JS-heavy sites (Univision, Telemundo) that don't have RSS feeds.
"""

import json
import logging
import hashlib
from datetime import datetime
from typing import List, Dict, Optional

from config import CLOAKBROWSER_PATH

logger = logging.getLogger(__name__)

CLOAKBRIDGE_SCRIPT = str(CLOAKBROWSER_PATH.parent / "pipeline" / "scraper" / "cloakbridge.mjs")

# Fallback: also check direct path
import os
if not os.path.exists(CLOAKBRIDGE_SCRIPT):
    # Try relative to this file
    CLOAKBRIDGE_SCRIPT = str(os.path.join(os.path.dirname(__file__), "cloakbridge.mjs"))


def url_hash(url: str) -> str:
    """Generate SHA256 hash of URL for deduplication."""
    return hashlib.sha256(url.encode()).hexdigest()


async def scrape_browser_links(
    target_url: str,
    link_selector: str,
    source_name: str,
    category_hint: str = "",
) -> List[Dict]:
    """
    Scrape article links from a listing page using CloakBrowser.
    Returns list of article dicts with url, title, image_url.
    """
    import asyncio

    config = json.dumps({
        "url": target_url,
        "link_selector": link_selector,
        "category_hint": category_hint,
    })

    logger.info(f"[Browser] Scraping links from {source_name}: {target_url}")

    try:
        proc = await asyncio.create_subprocess_exec(
            "node", CLOAKBRIDGE_SCRIPT, "scrape_links", config,
            cwd=str(CLOAKBROWSER_PATH),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

        if proc.returncode != 0:
            err = stderr.decode() if stderr else "unknown error"
            logger.error(f"[Browser] CloakBrowser failed for {source_name}: {err}")
            return []

        result = json.loads(stdout.decode())
        if isinstance(result, dict) and "error" in result:
            logger.error(f"[Browser] Error from {source_name}: {result['error']}")
            return []

        # Add metadata
        for item in result:
            item["source_name"] = source_name
            item["url_hash"] = url_hash(item.get("url", ""))
            item["discovered_at"] = datetime.utcnow()
            if "category_hint" not in item:
                item["category_hint"] = category_hint

        logger.info(f"[Browser] {source_name}: found {len(result)} links")
        return result

    except asyncio.TimeoutError:
        logger.error(f"[Browser] Timeout scraping {source_name}")
        return []
    except Exception as e:
        logger.error(f"[Browser] Error scraping {source_name}: {e}")
        return []


async def scrape_browser_article(
    article_url: str,
    content_config: Dict,
) -> Optional[Dict]:
    """
    Scrape full article content using CloakBrowser.
    content_config has selectors: title_selector, body_selector, etc.
    """
    import asyncio

    config = json.dumps({
        "url": article_url,
        "content_config": content_config,
    })

    logger.info(f"[Browser] Scraping article: {article_url[:80]}...")

    try:
        proc = await asyncio.create_subprocess_exec(
            "node", CLOAKBRIDGE_SCRIPT, "scrape_article", config,
            cwd=str(CLOAKBROWSER_PATH),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=90)

        if proc.returncode != 0:
            err = stderr.decode() if stderr else "unknown error"
            logger.error(f"[Browser] Article scrape failed: {err}")
            return None

        result = json.loads(stdout.decode())

        if isinstance(result, dict) and "error" in result:
            logger.error(f"[Browser] Article error: {result['error']}")
            return None

        # Add hash
        result["url_hash"] = url_hash(article_url)
        result["discovered_at"] = datetime.utcnow()

        return result

    except asyncio.TimeoutError:
        logger.error(f"[Browser] Timeout scraping article {article_url}")
        return None
    except Exception as e:
        logger.error(f"[Browser] Error scraping article: {e}")
        return None
