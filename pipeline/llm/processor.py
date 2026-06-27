"""
LLM Pipeline Processor — The 4-step article rewriting engine.

Steps per article:
  1. CLASSIFY: Determine category, content type, relevance
  2. REWRITE (ES): Rewrite article in Spanish with Latinos.org voice
  3. REWRITE (EN): Generate English version
  4. METADATA: Generate SEO title, slug, tags, excerpt
  5. QA: Quality check — fidelity, originality, hallucination detection

Processes multiple articles concurrently via asyncio.Semaphore.
"""

import asyncio
import json
import logging
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple

import httpx

from config import VLLM_BASE_URL, VLLM_MODEL, PROMPTS_DIR, LLM_CONCURRENCY
from llm.client import chat_completion, check_health, SAMPLING_PARAMS

logger = logging.getLogger(__name__)

# Load prompt templates
def _load_prompt(name: str) -> str:
    path = PROMPTS_DIR / f"{name}.txt"
    return path.read_text(encoding="utf-8")

PROMPT_CLASSIFY = _load_prompt("classify")
PROMPT_REWRITE_ES = _load_prompt("rewrite_es")
PROMPT_REWRITE_EN = _load_prompt("rewrite_en")
PROMPT_METADATA = _load_prompt("metadata")
PROMPT_QA = _load_prompt("quality_check")


# === JSON extraction helper ===
def extract_json(text: str) -> Optional[dict]:
    """Extract a JSON object from LLM text response (handles markdown code fences)."""
    if not text:
        return None

    # Strip markdown code fences if present
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = text.replace("```", "")

    # Try direct parse first
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    # Find first { ... last }
    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last != -1 and last > first:
        try:
            return json.loads(text[first:last + 1])
        except json.JSONDecodeError:
            pass

    return None


def slugify(text: str) -> str:
    """Convert text to URL-safe slug."""
    # Remove accents
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ASCII", "ignore").decode("ASCII")
    # Lowercase, replace spaces/special chars with hyphens
    text = re.sub(r"[^\w\s-]", "", text.lower())
    text = re.sub(r"[\s_-]+", "-", text).strip("-")
    # Truncate
    return text[:80]


def truncate_text(text: str, max_chars: int = 4000) -> str:
    """Truncate text to fit within LLM context limits."""
    if len(text) <= max_chars:
        return text
    # Try to cut at a sentence boundary
    cut = text[:max_chars]
    last_period = cut.rfind(". ")
    if last_period > max_chars * 0.7:
        return cut[:last_period + 1]
    return cut + "..."


# === Step 1: Classify ===
async def step_classify(title: str, body_text: str) -> Optional[dict]:
    """Classify article into category and type."""
    content = f"TÍTULO: {title}\n\nCONTENIDO:\n{truncate_text(body_text, 3000)}"

    response = await chat_completion(PROMPT_CLASSIFY, content)
    if not response:
        return None

    result = extract_json(response)
    if not result:
        logger.warning(f"[Classify] Could not parse JSON from response")
        return None

    return result


# === Step 2: Rewrite Spanish ===
async def step_rewrite_es(title: str, body_text: str, classification: dict) -> Optional[str]:
    """Rewrite article in Spanish with Latinos.org voice."""
    context = ""
    if classification.get("category"):
        context += f"\nCategoría asignada: {classification['category']}"
    if classification.get("summary"):
        context += f"\nResumen del tema: {classification['summary']}"

    content = f"ARTÍCULO ORIGINAL:\nTítulo: {title}\n\n{truncate_text(body_text, 6000)}{context}"

    response = await chat_completion(PROMPT_REWRITE_ES, content)
    return response


# === Step 3: Rewrite English ===
async def step_rewrite_en(es_title: str, es_body: str) -> Optional[str]:
    """Generate English version of the rewritten article."""
    content = f"ARTÍCULO EN ESPAÑOL:\nTítulo: {es_title}\n\n{truncate_text(es_body, 6000)}"

    response = await chat_completion(PROMPT_REWRITE_EN, content)
    return response


# === Step 4: Metadata ===
async def step_metadata(es_body: str) -> Optional[dict]:
    """Generate SEO metadata for the article."""
    content = f"ARTÍCULO:\n{truncate_text(es_body, 4000)}"

    response = await chat_completion(PROMPT_METADATA, content)
    if not response:
        return None

    result = extract_json(response)
    if not result:
        logger.warning("[Metadata] Could not parse JSON")
        return None

    return result


# === Step 5: Quality Check ===
async def step_quality_check(original_text: str, rewritten_text: str) -> Optional[dict]:
    """Run quality assurance check on rewritten content."""
    content = (
        f"ARTÍCULO ORIGINAL:\n{truncate_text(original_text, 3000)}\n\n"
        f"ARTÍCULO REESCRITO:\n{truncate_text(rewritten_text, 3000)}"
    )

    response = await chat_completion(PROMPT_QA, content)
    if not response:
        return None

    result = extract_json(response)
    if not result:
        logger.warning("[QA] Could not parse JSON")
        return {"quality_score": 0.5, "recommendation": "review"}

    return result


# === Full Article Processing ===
async def process_article(raw_article: dict) -> Optional[dict]:
    """
    Process a single raw article through the full pipeline.
    Accepts a plain dict with: id, title, extracted_text, etc.
    Returns a dict with all processed data, or None on failure.
    """
    raw_id = raw_article["id"]
    title = raw_article.get("title") or "Untitled"
    body = raw_article.get("extracted_text") or ""

    if len(body) < 100:
        logger.warning(f"[Article {raw_id}] Body too short ({len(body)} chars), skipping")
        return None

    logger.info(f"[Article {raw_id}] Processing: {title[:60]}...")

    # Step 1: Classify
    classification = await step_classify(title, body)
    if not classification:
        logger.error(f"[Article {raw_id}] Classification failed")
        return None

    logger.info(f"[Article {raw_id}] → Category: {classification.get('category')}, "
                f"Type: {classification.get('content_type')}")

    # Step 2: Rewrite Spanish
    es_article = await step_rewrite_es(title, body, classification)
    if not es_article or len(es_article) < 100:
        logger.error(f"[Article {raw_id}] Spanish rewrite failed")
        return None

    # Extract title from rewritten article (first line, typically)
    es_title = es_article.split("\n")[0].strip().strip("#").strip()
    if not es_title or len(es_title) > 300:
        es_title = title  # Fallback to original

    # Step 3+4: Run EN rewrite and metadata concurrently
    en_task = step_rewrite_en(es_title, es_article)
    meta_task = step_metadata(es_article)

    en_result, meta_result = await asyncio.gather(en_task, meta_task, return_exceptions=True)

    # Handle EN
    en_article = None
    en_title = None
    if isinstance(en_result, str) and len(en_result) > 100:
        en_article = en_result
        en_title = en_result.split("\n")[0].strip().strip("#").strip()
        if not en_title or len(en_title) > 300:
            en_title = es_title
    elif isinstance(en_result, Exception):
        logger.warning(f"[Article {raw_id}] EN rewrite error: {en_result}")

    # Handle metadata
    metadata = meta_result if isinstance(meta_result, dict) else {}
    if isinstance(meta_result, Exception):
        logger.warning(f"[Article {raw_id}] Metadata error: {meta_result}")
        metadata = {}

    # Generate slug
    slug = metadata.get("slug") or slugify(es_title)
    if not slug:
        slug = slugify(title)

    # Step 5: Quality check
    qa = await step_quality_check(body, es_article)
    if not qa:
        qa = {"quality_score": 0.5, "recommendation": "review"}

    logger.info(f"[Article {raw_id}] QA Score: {qa.get('quality_score', '?')}, "
                f"Recommendation: {qa.get('recommendation', '?')}")

    # Assemble final result
    return {
        "raw_article_id": raw_id,
        "classification": classification,
        "es_title": es_title,
        "es_body": es_article,
        "en_title": en_title,
        "en_body": en_article,
        "metadata": metadata,
        "qa": qa,
        "slug": slug,
        "quality_score": qa.get("quality_score", 0.5),
    }


def save_processed_article(session, result: dict, source_name: str = ""):
    """
    Save a processed article to the articles table.
    Creates a draft article ready for admin review.
    """
    from models import Article, Category

    classification = result.get("classification", {})
    metadata = result.get("metadata", {})
    qa = result.get("qa", {})

    # Find or create category
    category_slug = classification.get("category", "noticias")
    category = session.query(Category).filter(Category.slug == category_slug).first()

    # Generate unique slug
    base_slug = result.get("slug") or slugify(result.get("es_title", "articulo"))
    slug = base_slug
    counter = 1
    while session.query(Article).filter(Article.slug == slug).first():
        slug = f"{base_slug}-{counter}"
        counter += 1

    # Extract tags
    tags = metadata.get("tags", [])
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except json.JSONDecodeError:
            tags = [tags]

    # Source image
    image_urls = []
    raw = session.query(Article).filter(
        Article.raw_article_id == result["raw_article_id"]
    ).first()

    # Get image from raw article
    from models import RawArticle
    raw_art = session.get(RawArticle, result["raw_article_id"])
    if raw_art and raw_art.image_urls:
        try:
            image_urls = json.loads(raw_art.image_urls)
        except json.JSONDecodeError:
            pass

    image_url = image_urls[0] if image_urls else None

    # Determine status
    recommendation = qa.get("recommendation", "review")
    if recommendation == "publish" and qa.get("quality_score", 0) >= 0.8:
        status = "pending_review"  # Always go through review first
    else:
        status = "pending_review"

    article = Article(
        raw_article_id=result["raw_article_id"],
        category_id=category.id if category else None,
        title=result["es_title"],
        slug=slug,
        body_markdown=result["es_body"],
        excerpt=metadata.get("excerpt", ""),
        title_en=result.get("en_title"),
        body_markdown_en=result.get("en_body"),
        excerpt_en="",
        meta_description=metadata.get("meta_description", ""),
        tags=json.dumps(tags, ensure_ascii=False),
        language="bilingual" if result.get("en_body") else "es",
        author_display="Latinos.org",
        source_credit=source_name or (raw_art.source_url if raw_art else ""),
        image_url=image_url,
        image_alt=metadata.get("image_alt", ""),
        quality_score=result.get("quality_score", 0.5),
        content_type=classification.get("content_type", "news"),
        status=status,
        is_breaking=classification.get("is_breaking", False),
        created_at=datetime.utcnow(),
    )

    session.add(article)
    return article
