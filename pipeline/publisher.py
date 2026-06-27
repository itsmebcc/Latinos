"""
Latinos.org — Publisher and Railway sync pipeline.

This is the final local-only publishing step:
1. Publish approved/scheduled articles in SQLite.
2. Download and optimize article images into website/static/images/articles/.
3. Write a deployment manifest for auditability.
4. Checkpoint SQLite WAL data into latinos.db.
5. Optionally commit and push deployable website artifacts so Railway auto-deploys.

The public Railway app remains read-only. This module only runs locally.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urlparse

import httpx
from PIL import Image, ImageOps, UnidentifiedImageError

# Make website modules importable.
PIPELINE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PIPELINE_DIR.parent
WEBSITE_DIR = PROJECT_ROOT / "website"
sys.path.insert(0, str(WEBSITE_DIR))

from database import DB_PATH, SessionLocal, engine  # noqa: E402
from models import Article, PipelineRun, RawArticle  # noqa: E402

IMAGES_DIR = WEBSITE_DIR / "static" / "images" / "articles"
MANIFEST_PATH = WEBSITE_DIR / "data" / "publish_manifest.json"
DEPLOY_PATHS = [
    "website/data/latinos.db",
    "website/data/publish_manifest.json",
    "website/static/images/articles",
]

IMAGE_MAX_WIDTH = int(os.environ.get("PUBLISHER_IMAGE_MAX_WIDTH", "1400"))
IMAGE_MAX_HEIGHT = int(os.environ.get("PUBLISHER_IMAGE_MAX_HEIGHT", "900"))
IMAGE_QUALITY = int(os.environ.get("PUBLISHER_IMAGE_QUALITY", "82"))
HTTP_TIMEOUT = float(os.environ.get("PUBLISHER_HTTP_TIMEOUT", "20"))


@dataclass
class PublishResult:
    articles_published: int = 0
    articles_processed: int = 0
    images_downloaded: int = 0
    images_skipped: int = 0
    images_failed: int = 0
    manifest_path: str = str(MANIFEST_PATH)
    committed: bool = False
    pushed: bool = False
    commit_sha: Optional[str] = None
    message: str = ""


def slug_part(value: str, max_len: int = 70) -> str:
    """Return a filesystem-safe slug fragment."""
    cleaned = []
    for ch in (value or "article").lower():
        if ch.isalnum():
            cleaned.append(ch)
        elif ch in {" ", "-", "_"}:
            cleaned.append("-")
    slug = "".join(cleaned).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return (slug or "article")[:max_len].strip("-") or "article"


def parse_image_candidates(article: Article, raw: Optional[RawArticle]) -> list[str]:
    """Return remote image candidates in priority order."""
    candidates: list[str] = []

    if article.image_url and article.image_url.startswith(("http://", "https://")):
        candidates.append(article.image_url)

    if raw and raw.image_urls:
        try:
            parsed = json.loads(raw.image_urls)
            if isinstance(parsed, str):
                parsed = [parsed]
            if isinstance(parsed, list):
                for url in parsed:
                    if isinstance(url, str) and url.startswith(("http://", "https://")):
                        candidates.append(url)
        except json.JSONDecodeError:
            pass

    # Deduplicate while preserving order.
    seen = set()
    unique = []
    for url in candidates:
        if url not in seen:
            seen.add(url)
            unique.append(url)
    return unique


def is_relative_local_image(url: Optional[str]) -> bool:
    return bool(url and url.startswith("/static/images/articles/"))


def image_output_path(article: Article, source_url: str) -> Path:
    digest = hashlib.sha256(source_url.encode("utf-8")).hexdigest()[:12]
    safe_slug = slug_part(article.slug or article.title or f"article-{article.id}")
    return IMAGES_DIR / f"{article.id}-{safe_slug}-{digest}.webp"


def download_one_image(article: Article, raw: Optional[RawArticle]) -> tuple[bool, Optional[str], str]:
    """
    Download/optimize a single image for an article.
    Returns (success, relative_path, message).
    """
    if is_relative_local_image(article.image_url):
        return False, article.image_url, "already-local"

    candidates = parse_image_candidates(article, raw)
    if not candidates:
        return False, None, "no-candidates"

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/126 Safari/537.36",
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    }

    last_error = ""
    for url in candidates:
        out_path = image_output_path(article, url)
        rel_path = f"/static/images/articles/{out_path.name}"
        if out_path.exists() and out_path.stat().st_size > 0:
            article.image_url = rel_path
            return True, rel_path, "already-downloaded"

        try:
            with httpx.Client(timeout=HTTP_TIMEOUT, follow_redirects=True, headers=headers) as client:
                resp = client.get(url)
                resp.raise_for_status()
                content = resp.content

            # SVGs are not converted by Pillow; store safely as-is only if explicit SVG.
            content_type = resp.headers.get("content-type", "").split(";")[0].lower()
            guessed_ext = mimetypes.guess_extension(content_type) or ""
            if content_type == "image/svg+xml" or guessed_ext == ".svg":
                svg_path = out_path.with_suffix(".svg")
                svg_path.write_bytes(content)
                rel_svg = f"/static/images/articles/{svg_path.name}"
                article.image_url = rel_svg
                return True, rel_svg, "downloaded-svg"

            tmp_path = out_path.with_suffix(".download")
            tmp_path.write_bytes(content)

            try:
                with Image.open(tmp_path) as img:
                    img = ImageOps.exif_transpose(img)
                    img.thumbnail((IMAGE_MAX_WIDTH, IMAGE_MAX_HEIGHT), Image.Resampling.LANCZOS)
                    if img.mode not in ("RGB", "RGBA"):
                        img = img.convert("RGB")
                    if img.mode == "RGBA":
                        background = Image.new("RGB", img.size, (255, 255, 255))
                        background.paste(img, mask=img.split()[-1])
                        img = background
                    img.save(out_path, "WEBP", quality=IMAGE_QUALITY, method=6)
            finally:
                tmp_path.unlink(missing_ok=True)

            article.image_url = rel_path
            return True, rel_path, "downloaded-webp"

        except (httpx.HTTPError, OSError, UnidentifiedImageError, ValueError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            continue

    return False, None, last_error or "download-failed"


def publish_ready_articles(session) -> int:
    """Move approved/scheduled-ready articles to published."""
    now = datetime.utcnow()
    ready = session.query(Article).filter(Article.status == "approved").all()
    scheduled = session.query(Article).filter(
        Article.status == "scheduled",
        Article.scheduled_for <= now,
    ).all()

    count = 0
    for article in [*ready, *scheduled]:
        article.status = "published"
        article.published_at = article.published_at or now
        article.approved_at = article.approved_at or now
        count += 1
    return count


def checkpoint_sqlite() -> None:
    """Ensure WAL changes are checkpointed into latinos.db before git add."""
    from sqlalchemy import text

    with engine.connect() as conn:
        conn.execute(text("PRAGMA wal_checkpoint(TRUNCATE)"))
        conn.execute(text("PRAGMA optimize"))


def write_manifest(session, result: PublishResult) -> None:
    """Write a small public-safe manifest for deploy auditing."""
    published_count = session.query(Article).filter(Article.status == "published").count()
    pending_review = session.query(Article).filter(Article.status == "pending_review").count()
    approved = session.query(Article).filter(Article.status == "approved").count()
    latest = session.query(Article).filter(Article.status == "published").order_by(Article.published_at.desc()).limit(10).all()

    manifest = {
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "database": str(DB_PATH.relative_to(PROJECT_ROOT)),
        "counts": {
            "published": published_count,
            "pending_review": pending_review,
            "approved": approved,
        },
        "latest_published": [
            {
                "id": a.id,
                "slug": a.slug,
                "title": a.title,
                "quality_score": a.quality_score,
                "published_at": a.published_at.isoformat() if a.published_at else None,
                "image_url": a.image_url,
            }
            for a in latest
        ],
        "last_run": asdict(result),
    }
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def git(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=PROJECT_ROOT,
        check=check,
        capture_output=True,
        text=True,
    )


def git_sync(result: PublishResult, push: bool = False, message: Optional[str] = None) -> PublishResult:
    """Commit deployable artifacts and optionally push to origin/main."""
    for path in DEPLOY_PATHS:
        full = PROJECT_ROOT / path
        if full.exists():
            git(["add", path])

    status = git(["status", "--porcelain", *DEPLOY_PATHS], check=False).stdout.strip()
    if not status:
        result.message = "No deployable changes to commit."
        return result

    commit_message = message or (
        "chore: publish latest Latinos.org content\n\n"
        f"- Published articles: {result.articles_published}\n"
        f"- Processed articles: {result.articles_processed}\n"
        f"- Images downloaded: {result.images_downloaded}\n"
        "- Sync SQLite DB and static article images for Railway"
    )
    existing_paths = [path for path in DEPLOY_PATHS if (PROJECT_ROOT / path).exists()]
    # --only prevents any unrelated pre-staged files from leaking into an auto-deploy commit.
    git(["commit", "--only", "-m", commit_message, "--", *existing_paths])
    result.committed = True
    result.commit_sha = git(["rev-parse", "--short", "HEAD"]).stdout.strip()

    if push:
        git(["push", "origin", "main"])
        result.pushed = True
        result.message = "Committed and pushed. Railway should auto-deploy from GitHub."
    else:
        result.message = "Committed locally. Run with --push to trigger Railway auto-deploy."
    return result


def run_publish(download_images: bool = True, commit: bool = False, push: bool = False) -> PublishResult:
    """Run the full publish/export/sync preparation pipeline."""
    result = PublishResult()
    session = SessionLocal()
    run = PipelineRun(run_type="publish", status="running", started_at=datetime.utcnow())
    session.add(run)
    session.commit()

    try:
        result.articles_published = publish_ready_articles(session)

        published_articles = session.query(Article).filter(Article.status == "published").all()
        result.articles_processed = len(published_articles)

        if download_images:
            for article in published_articles:
                raw = session.get(RawArticle, article.raw_article_id) if article.raw_article_id else None
                changed, rel_path, msg = download_one_image(article, raw)
                if changed and rel_path:
                    result.images_downloaded += 1
                elif msg in {"already-local", "already-downloaded", "no-candidates"}:
                    result.images_skipped += 1
                else:
                    result.images_failed += 1

        session.commit()
        write_manifest(session, result)
        checkpoint_sqlite()

        run.status = "completed"
        run.completed_at = datetime.utcnow()
        run.articles_processed = result.articles_processed
        run.articles_succeeded = result.articles_processed
        run.articles_failed = result.images_failed
        session.commit()

    except Exception as exc:
        session.rollback()
        run.status = "failed"
        run.completed_at = datetime.utcnow()
        run.error_log = f"{type(exc).__name__}: {exc}"
        session.commit()
        raise
    finally:
        session.close()

    if commit or push:
        result = git_sync(result, push=push)
    else:
        result.message = "Publish export complete. Use --commit or --push to sync Railway artifacts."

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish Latinos.org approved content and sync deploy artifacts.")
    parser.add_argument("--no-images", action="store_true", help="Skip image download/optimization")
    parser.add_argument("--commit", action="store_true", help="Commit deployable website artifacts")
    parser.add_argument("--push", action="store_true", help="Commit and push deployable website artifacts")
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    args = parser.parse_args()

    result = run_publish(download_images=not args.no_images, commit=args.commit or args.push, push=args.push)

    if args.json:
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    else:
        print("=== Latinos.org Publisher ===")
        print(f"Published newly-ready articles: {result.articles_published}")
        print(f"Published articles processed:   {result.articles_processed}")
        print(f"Images downloaded/optimized:   {result.images_downloaded}")
        print(f"Images skipped:                {result.images_skipped}")
        print(f"Images failed:                 {result.images_failed}")
        print(f"Manifest:                      {result.manifest_path}")
        print(f"Committed:                     {result.committed}")
        print(f"Pushed:                        {result.pushed}")
        if result.commit_sha:
            print(f"Commit:                        {result.commit_sha}")
        print(result.message)


if __name__ == "__main__":
    main()
