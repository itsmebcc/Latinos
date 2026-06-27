"""
RSS Feed Scraper — Ingests articles from RSS/Atom feeds.
Fast, lightweight, runs every 15 minutes.
Supports all sites with public feeds: AS USA, Marca, Remezcla, Mitú, Latino Rebels.
"""

import hashlib
import logging
from datetime import datetime
from typing import List, Dict, Optional
from xml.etree import ElementTree as ET

import httpx

logger = logging.getLogger(__name__)

# Namespaces for parsing media-rich feeds
NAMESPACES = {
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "media": "http://search.yahoo.com/mrss/",
    "dcterms": "http://purl.org/dc/terms/",
    "atom": "http://www.w3.org/2005/Atom/",
}


def url_hash(url: str) -> str:
    """Generate SHA256 hash of URL for deduplication."""
    return hashlib.sha256(url.encode()).hexdigest()


async def fetch_feed(feed_url: str, timeout: int = 30) -> Optional[str]:
    """Fetch RSS/Atom feed XML content."""
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    }
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
            response = await client.get(feed_url, headers=headers)
            if response.status_code == 200:
                return response.text
            else:
                logger.warning(f"Feed {feed_url} returned HTTP {response.status_code}")
                return None
    except Exception as e:
        logger.error(f"Error fetching feed {feed_url}: {e}")
        return None


def extract_items(xml_text: str) -> List[Dict]:
    """
    Parse RSS/Atom XML and extract article items.
    Handles both RSS 2.0 and Atom feeds.
    Falls back to feedparser for malformed XML.
    """
    items = []

    # First try strict XML parsing
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        logger.warning(f"Strict XML parse failed ({e}), trying feedparser fallback")
        return _parse_with_feedparser(xml_text)

    # RSS 2.0: //item
    rss_items = root.findall(".//item")
    for item in rss_items:
        extracted = _parse_rss_item(item)
        if extracted:
            items.append(extracted)

    # Atom: //entry
    if not items:
        atom_entries = root.findall(".//{http://www.w3.org/2005/Atom}entry")
        for entry in atom_entries:
            extracted = _parse_atom_entry(entry)
            if extracted:
                items.append(extracted)

    # If strict parsing found nothing, try feedparser
    if not items:
        logger.warning("Strict parsing found no items, trying feedparser")
        return _parse_with_feedparser(xml_text)

    return items


def _parse_with_feedparser(xml_text: str) -> List[Dict]:
    """Fallback parser using feedparser library (handles malformed XML)."""
    try:
        import feedparser
        feed = feedparser.parse(xml_text)
        items = []
        for entry in feed.entries:
            link = entry.get("link", "")
            if not link:
                continue

            # Get best available text
            body_text = ""
            if hasattr(entry, "content") and entry.content:
                body_text = entry.content[0].get("value", "")
            elif hasattr(entry, "summary"):
                body_text = entry.summary

            # Get image
            image_url = None
            if hasattr(entry, "media_content") and entry.media_content:
                image_url = entry.media_content[0].get("url")
            elif hasattr(entry, "links"):
                for link_item in entry.links:
                    if link_item.get("type", "").startswith("image"):
                        image_url = link_item.get("href")
                        break

            # Author
            author = ""
            if hasattr(entry, "author"):
                author = entry.author
            elif hasattr(entry, "author_detail") and entry.author_detail:
                author = entry.author_detail.get("name", "")

            items.append({
                "url": link,
                "url_hash": url_hash(link),
                "title": entry.get("title", ""),
                "description": entry.get("summary", ""),
                "body_text": body_text,
                "author": author,
                "publish_date": parse_date(entry.get("published")),
                "image_url": image_url,
                "categories": [tag.get("term", "") for tag in entry.get("tags", [])],
            })
        logger.info(f"[feedparser] Extracted {len(items)} items")
        return items
    except Exception as e:
        logger.error(f"feedparser fallback failed: {e}")
        return []


def parse_date(date_str: Optional[str]) -> Optional[datetime]:
    """Parse various date formats found in RSS feeds."""
    if not date_str:
        return None

    date_str = date_str.strip()

    # Try common RSS date formats
    formats = [
        "%a, %d %b %Y %H:%M:%S GMT",
        "%a, %d %b %Y %H:%M:%S +0000",
        "%a, %d %b %Y %H:%M:%S %z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue

    # Try email.utils.parsedate_to_datetime as fallback
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(date_str)
    except Exception:
        pass

    logger.debug(f"Could not parse date: {date_str}")
    return None


def extract_items_OLD_REMOVED(xml_text: str) -> List[Dict]:
    """DELETED — replaced by extract_items above with feedparser fallback."""
    return []


def _get_text(element, tag: str, namespace: str = "") -> Optional[str]:
    """Safely get text from an XML element."""
    if namespace:
        tag = f"{namespace}:{tag}"
    child = element.find(tag, NAMESPACES)
    if child is not None and child.text:
        return child.text.strip()
    return None


def _parse_rss_item(item) -> Optional[Dict]:
    """Parse a single RSS 2.0 <item> element."""
    link = _get_text(item, "link")
    if not link:
        # Some feeds use guid as link
        guid = item.find("guid")
        if guid is not None and guid.text:
            link = guid.text.strip()

    if not link:
        return None

    title = _get_text(item, "title")
    description = _get_text(item, "description")

    # Try content:encoded for full text (WordPress feeds)
    content_encoded = _get_text(item, "encoded", "content")
    body_text = content_encoded or description or ""

    author = (
        _get_text(item, "creator", "dc")
        or _get_text(item, "author")
        or ""
    )

    pub_date_str = _get_text(item, "pubDate")
    pub_date = parse_date(pub_date_str)

    # Extract image from media:content or enclosure
    image_url = None
    media_content = item.find("media:content", NAMESPACES)
    if media_content is not None:
        image_url = media_content.get("url")
    if not image_url:
        enclosure = item.find("enclosure")
        if enclosure is not None:
            image_url = enclosure.get("url")
    if not image_url and content_encoded:
        # Try to find first img tag in content
        import re
        img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', content_encoded)
        if img_match:
            image_url = img_match.group(1)

    # Extract categories/tags
    categories = []
    for cat in item.findall("category"):
        if cat.text:
            categories.append(cat.text.strip())

    return {
        "url": link,
        "url_hash": url_hash(link),
        "title": title or "",
        "description": description or "",
        "body_text": body_text,
        "author": author,
        "publish_date": pub_date,
        "image_url": image_url,
        "categories": categories,
    }


def _parse_atom_entry(entry) -> Optional[Dict]:
    """Parse a single Atom <entry> element."""
    ns = "{http://www.w3.org/2005/Atom}"

    link_elem = entry.find(f"{ns}link")
    link = link_elem.get("href") if link_elem is not None else None
    if not link:
        return None

    title_elem = entry.find(f"{ns}title")
    title = title_elem.text.strip() if title_elem is not None and title_elem.text else ""

    summary_elem = entry.find(f"{ns}summary")
    summary = summary_elem.text if summary_elem is not None and summary_elem.text else ""

    content_elem = entry.find(f"{ns}content")
    content = content_elem.text if content_elem is not None and content_elem.text else ""

    author_elem = entry.find(f"{ns}author/{ns}name")
    author = author_elem.text if author_elem is not None and author_elem.text else ""

    date_str = None
    updated = entry.find(f"{ns}updated")
    if updated is not None and updated.text:
        date_str = updated.text
    published = entry.find(f"{ns}published")
    if published is not None and published.text:
        date_str = published.text

    pub_date = parse_date(date_str)

    return {
        "url": link,
        "url_hash": url_hash(link),
        "title": title,
        "description": summary,
        "body_text": content or summary,
        "author": author,
        "publish_date": pub_date,
        "image_url": None,
        "categories": [],
    }


async def scrape_rss_feed(
    feed_url: str,
    source_name: str,
    category_hint: str = "",
    max_items: int = 30,
) -> List[Dict]:
    """
    Full pipeline: fetch and parse an RSS feed.
    Returns list of article dicts ready for database insertion.
    """
    logger.info(f"[RSS] Fetching {source_name}: {feed_url}")

    xml_text = await fetch_feed(feed_url)
    if not xml_text:
        return []

    items = extract_items(xml_text)
    logger.info(f"[RSS] {source_name}: found {len(items)} items in feed")

    # Limit items per run
    items = items[:max_items]

    # Add metadata
    for item in items:
        item["source_name"] = source_name
        item["category_hint"] = category_hint
        item["discovered_at"] = datetime.utcnow()

    return items
