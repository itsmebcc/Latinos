"""
Latinos.org — Admin Portal Routes.
Dashboard, review queue, article editing, approval, publishing.
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy import select, func, desc, and_
from sqlalchemy.orm import joinedload

from auth import check_auth, require_auth, get_session_token, verify_password, create_session, destroy_session
from models import Article, Category, RawArticle, Source, PipelineRun

router = APIRouter()
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PIPELINE_DIR = PROJECT_ROOT / "pipeline"


def get_db():
    """Get DB session — uses website database module."""
    from database import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ============= LOGIN =============

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if check_auth(request):
        return RedirectResponse("/dashboard", status_code=303)
    return request.app.state.templates.TemplateResponse("login.html", {
        "request": request, "error": None
    })


@router.post("/login")
async def login_submit(request: Request, password: str = Form(...)):
    if verify_password(password):
        token = create_session()
        response = RedirectResponse("/dashboard", status_code=303)
        response.set_cookie("latinos_admin_session", token, httponly=True, max_age=43200)
        return response
    return request.app.state.templates.TemplateResponse("login.html", {
        "request": request, "error": "Contraseña incorrecta"
    })


@router.get("/logout")
async def logout(request: Request):
    token = get_session_token(request)
    if token:
        destroy_session(token)
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("latinos_admin_session")
    return response


# ============= DASHBOARD =============

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    require_auth(request)
    db = next(get_db())

    # Pipeline stats
    total_raw = db.query(RawArticle).count()
    pending_scrape = db.query(RawArticle).filter(RawArticle.status == "discovered").count()
    processing = db.query(RawArticle).filter(RawArticle.status == "processing").count()
    rewritten = db.query(RawArticle).filter(RawArticle.status == "rewritten").count()

    # Article stats
    total_articles = db.query(Article).count()
    pending_review = db.query(Article).filter(Article.status == "pending_review").count()
    published = db.query(Article).filter(Article.status == "published").count()
    drafts = db.query(Article).filter(Article.status == "draft").count()
    approved = db.query(Article).filter(Article.status == "approved").count()

    # Average quality
    avg_quality = db.query(func.avg(Article.quality_score)).filter(
        Article.status == "pending_review"
    ).scalar() or 0

    # Recent pipeline runs
    runs = db.query(PipelineRun).order_by(desc(PipelineRun.id)).limit(10).all()

    # Sources
    sources = db.query(Source).all()
    source_stats = []
    for src in sources:
        count = db.query(RawArticle).filter(RawArticle.source_id == src.id).count()
        source_stats.append({"name": src.name, "domain": src.domain, "count": count, "active": src.is_active})

    # Recent pending articles (eagerly load category to avoid detached session errors)
    recent_pending = db.query(Article).options(
        joinedload(Article.category_rel)
    ).filter(
        Article.status == "pending_review"
    ).order_by(desc(Article.created_at)).limit(5).all()

    db.close()

    return request.app.state.templates.TemplateResponse("dashboard.html", {
        "request": request,
        "total_raw": total_raw,
        "pending_scrape": pending_scrape,
        "processing": processing,
        "rewritten": rewritten,
        "total_articles": total_articles,
        "pending_review": pending_review,
        "published": published,
        "drafts": drafts,
        "approved": approved,
        "avg_quality": round(avg_quality, 2),
        "runs": runs,
        "source_stats": source_stats,
        "recent_pending": recent_pending,
    })


# ============= REVIEW QUEUE =============

@router.get("/review", response_class=HTMLResponse)
async def review_queue(
    request: Request,
    status: str = Query("pending_review"),
    category: int = Query(0),
    min_score: float = Query(0.0),
    sort: str = Query("newest"),
):
    require_auth(request)
    db = next(get_db())

    query = db.query(Article).options(joinedload(Article.category_rel))

    # Filter by status
    if status != "all":
        query = query.filter(Article.status == status)

    # Filter by category
    if category > 0:
        query = query.filter(Article.category_id == category)

    # Filter by quality score
    if min_score > 0:
        query = query.filter(Article.quality_score >= min_score)

    # Sort
    if sort == "quality_desc":
        query = query.order_by(desc(Article.quality_score))
    elif sort == "quality_asc":
        query = query.order_by(Article.quality_score.asc())
    elif sort == "oldest":
        query = query.order_by(Article.created_at.asc())
    else:  # newest
        query = query.order_by(desc(Article.created_at))

    articles = query.limit(50).all()

    # Categories for filter dropdown
    categories = db.query(Category).order_by(Category.display_order).all()

    # Count by status for sidebar
    status_counts = {
        "pending_review": db.query(Article).filter(Article.status == "pending_review").count(),
        "draft": db.query(Article).filter(Article.status == "draft").count(),
        "published": db.query(Article).filter(Article.status == "published").count(),
        "approved": db.query(Article).filter(Article.status == "approved").count(),
        "rejected": db.query(Article).filter(Article.status == "rejected").count(),
    }

    db.close()

    return request.app.state.templates.TemplateResponse("review.html", {
        "request": request,
        "articles": articles,
        "categories": categories,
        "status_counts": status_counts,
        "filters": {"status": status, "category": category, "min_score": min_score, "sort": sort},
    })


# ============= ARTICLE DETAIL / EDIT =============

@router.get("/article/{article_id}", response_class=HTMLResponse)
async def article_detail(request: Request, article_id: int):
    require_auth(request)
    db = next(get_db())

    article = db.query(Article).options(
        joinedload(Article.category_rel)
    ).get(article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Artículo no encontrado")

    # Get the original raw article for side-by-side
    raw = None
    if article.raw_article_id:
        raw = db.query(RawArticle).get(article.raw_article_id)

    source = None
    if raw:
        source = db.query(Source).get(raw.source_id)

    # Parse tags
    tags = []
    if article.tags:
        try:
            tags = json.loads(article.tags)
        except json.JSONDecodeError:
            tags = []

    categories = db.query(Category).order_by(Category.display_order).all()

    db.close()

    return request.app.state.templates.TemplateResponse("article_detail.html", {
        "request": request,
        "article": article,
        "raw": raw,
        "source": source,
        "tags": tags,
        "categories": categories,
    })


@router.post("/article/{article_id}/save")
async def save_article(
    request: Request,
    article_id: int,
    title: str = Form(...),
    slug: str = Form(...),
    body_markdown: str = Form(...),
    excerpt: str = Form(""),
    meta_description: str = Form(""),
    category_id: int = Form(...),
    tags: str = Form(""),
    is_featured: bool = Form(False),
    is_breaking: bool = Form(False),
):
    require_auth(request)
    db = next(get_db())

    article = db.query(Article).get(article_id)
    if not article:
        raise HTTPException(status_code=404)

    article.title = title.strip()
    article.slug = slug.strip()
    article.body_markdown = body_markdown
    article.excerpt = excerpt.strip()
    article.meta_description = meta_description.strip()
    article.category_id = category_id
    article.is_featured = is_featured
    article.is_breaking = is_breaking

    # Parse tags (comma-separated input)
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    article.tags = json.dumps(tag_list, ensure_ascii=False)

    db.commit()
    db.close()

    return RedirectResponse(f"/article/{article_id}?saved=1", status_code=303)


@router.post("/article/{article_id}/approve")
async def approve_article(
    request: Request,
    article_id: int,
    publish_now: bool = Form(False),
):
    require_auth(request)
    db = next(get_db())

    article = db.query(Article).get(article_id)
    if not article:
        raise HTTPException(status_code=404)

    article.status = "published" if publish_now else "approved"
    article.approved_at = datetime.utcnow()
    if publish_now:
        article.published_at = datetime.utcnow()

    db.commit()
    db.close()

    return RedirectResponse("/review?status=pending_review", status_code=303)


@router.post("/article/{article_id}/publish")
async def publish_article(request: Request, article_id: int):
    require_auth(request)
    db = next(get_db())

    article = db.query(Article).get(article_id)
    if not article:
        raise HTTPException(status_code=404)

    article.status = "published"
    article.published_at = datetime.utcnow()

    db.commit()
    db.close()

    return RedirectResponse("/review?status=published", status_code=303)


@router.post("/article/{article_id}/reject")
async def reject_article(request: Request, article_id: int):
    require_auth(request)
    db = next(get_db())

    article = db.query(Article).get(article_id)
    if not article:
        raise HTTPException(status_code=404)

    article.status = "rejected"

    db.commit()
    db.close()

    return RedirectResponse("/review?status=pending_review", status_code=303)


@router.post("/article/{article_id}/delete")
async def delete_article(request: Request, article_id: int):
    require_auth(request)
    db = next(get_db())

    article = db.query(Article).get(article_id)
    if not article:
        raise HTTPException(status_code=404)

    db.delete(article)
    db.commit()
    db.close()

    return RedirectResponse("/review", status_code=303)


# ============= BULK OPERATIONS =============

@router.post("/bulk/action")
async def bulk_action(
    request: Request,
    action: str = Form(...),
    min_score: float = Form(0.0),
    max_score: float = Form(1.0),
    category_id: int = Form(0),
    status_filter: str = Form("pending_review"),
):
    require_auth(request)
    db = next(get_db())

    query = db.query(Article).filter(Article.status == status_filter)
    query = query.filter(Article.quality_score >= min_score)
    if max_score < 1.0:
        query = query.filter(Article.quality_score <= max_score)
    if category_id > 0:
        query = query.filter(Article.category_id == category_id)

    articles = query.all()
    count = 0
    now = datetime.utcnow()

    for article in articles:
        if action == "approve":
            article.status = "approved"
            article.approved_at = now
            count += 1
        elif action == "publish":
            article.status = "published"
            article.approved_at = now
            article.published_at = now
            count += 1
        elif action == "reject":
            article.status = "rejected"
            count += 1
        elif action == "delete":
            db.delete(article)
            count += 1

    db.commit()
    db.close()

    return JSONResponse({"action": action, "affected": count})


# ============= PUBLISH ALL APPROVED =============

@router.post("/publish-approved")
async def publish_all_approved(request: Request):
    """Publish all approved articles."""
    require_auth(request)
    db = next(get_db())

    articles = db.query(Article).filter(Article.status == "approved").all()
    now = datetime.utcnow()

    for article in articles:
        article.status = "published"
        article.published_at = now

    db.commit()
    count = len(articles)
    db.close()

    return JSONResponse({"published": count})


# ============= RAILWAY SYNC / PUBLISHER =============

@router.post("/publisher/run")
async def run_publisher_from_admin(
    request: Request,
    push: bool = Form(False),
):
    """
    Run the Phase 5 publisher from the local admin portal.

    This publishes approved/scheduled articles, downloads article images into
    website/static/images/articles, writes publish_manifest.json, commits the
    deployable artifacts, and optionally pushes to GitHub to trigger Railway.
    """
    require_auth(request)
    if str(PIPELINE_DIR) not in sys.path:
        sys.path.insert(0, str(PIPELINE_DIR))

    from publisher import run_publish

    try:
        result = run_publish(download_images=True, commit=True, push=push)
        return JSONResponse({
            "ok": True,
            "articles_published": result.articles_published,
            "articles_processed": result.articles_processed,
            "images_downloaded": result.images_downloaded,
            "images_skipped": result.images_skipped,
            "images_failed": result.images_failed,
            "committed": result.committed,
            "pushed": result.pushed,
            "commit_sha": result.commit_sha,
            "message": result.message,
        })
    except Exception as exc:
        return JSONResponse({
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        }, status_code=500)


@router.get("/publisher/manifest")
async def publisher_manifest(request: Request):
    """Return the latest local publish manifest."""
    require_auth(request)
    manifest_path = PROJECT_ROOT / "website" / "data" / "publish_manifest.json"
    if not manifest_path.exists():
        return JSONResponse({"ok": False, "error": "No publish manifest has been generated yet."}, status_code=404)
    return JSONResponse(json.loads(manifest_path.read_text(encoding="utf-8")))


# ============= RAW ARTICLES =============

@router.get("/raw-articles", response_class=HTMLResponse)
async def raw_articles_list(
    request: Request,
    status: str = Query("discovered"),
    page: int = Query(1, ge=1),
):
    require_auth(request)
    db = next(get_db())

    per_page = 50
    offset = (page - 1) * per_page

    query = db.query(RawArticle)
    if status != "all":
        query = query.filter(RawArticle.status == status)

    total = query.count()
    raws = query.order_by(desc(RawArticle.discovered_at)).offset(offset).limit(per_page).all()

    # Get source names
    source_map = {}
    sources = db.query(Source).all()
    for s in sources:
        source_map[s.id] = s.name

    total_pages = (total + per_page - 1) // per_page if total > 0 else 1

    db.close()

    return request.app.state.templates.TemplateResponse("raw_articles.html", {
        "request": request,
        "raws": raws,
        "source_map": source_map,
        "status": status,
        "page": page,
        "total_pages": total_pages,
        "total": total,
    })
