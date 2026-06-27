"""
Latinos.org — Public website routes.
Serves homepage, article pages, category pages, search, RSS, and sitemap.
"""

from datetime import datetime
from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import select, func, desc
from sqlalchemy.orm import Session

from models import Article, Category
from database import get_db

router = APIRouter()


# === Homepage ===
@router.get("/", response_class=HTMLResponse)
async def homepage(request: Request):
    db: Session = next(get_db())

    # Fetch all published content for the homepage
    # Breaking news
    breaking = db.execute(
        select(Article)
        .where(Article.status == "published")
        .where(Article.is_breaking == True)
        .order_by(desc(Article.published_at))
        .limit(5)
    ).scalars().all()

    # Hero/featured story (top non-breaking published article)
    hero = db.execute(
        select(Article)
        .where(Article.status == "published")
        .where(Article.is_featured == True)
        .order_by(desc(Article.published_at))
        .limit(1)
    ).scalars().first()

    # If no featured article, use the most recent
    if not hero:
        hero = db.execute(
            select(Article)
            .where(Article.status == "published")
            .order_by(desc(Article.published_at))
            .limit(1)
        ).scalars().first()

    # Main grid (exclude hero)
    hero_id = hero.id if hero else -1
    grid_articles = db.execute(
        select(Article)
        .where(Article.status == "published")
        .where(Article.id != hero_id)
        .order_by(desc(Article.published_at))
        .limit(8)
    ).scalars().all()

    # Category sections: fetch 4 latest per category
    categories = db.execute(
        select(Category)
        .where(Category.is_active == True)
        .order_by(Category.display_order)
    ).scalars().all()

    category_sections = []
    for cat in categories:
        articles = db.execute(
            select(Article)
            .where(Article.status == "published")
            .where(Article.category_id == cat.id)
            .order_by(desc(Article.published_at))
            .limit(4)
        ).scalars().all()
        if articles:
            category_sections.append({
                "category": cat,
                "articles": articles,
            })

    # Trending / Most viewed
    trending = db.execute(
        select(Article)
        .where(Article.status == "published")
        .order_by(desc(Article.view_count))
        .limit(5)
    ).scalars().all()

    return request.app.state.templates.TemplateResponse("index.html", {
        "request": request,
        "breaking": breaking,
        "hero": hero,
        "grid_articles": grid_articles,
        "category_sections": category_sections,
        "trending": trending,
        "categories": categories,
    })


# === Article page ===
@router.get("/articulo/{slug}", response_class=HTMLResponse)
async def article_page(request: Request, slug: str):
    db: Session = next(get_db())

    article = db.execute(
        select(Article).where(Article.slug == slug)
    ).scalars().first()

    if not article or article.status != "published":
        raise HTTPException(status_code=404, detail="Artículo no encontrado")

    # Increment view count
    article.view_count += 1
    db.commit()

    # Related articles (same category, exclude current)
    related = []
    if article.category_id:
        related = db.execute(
            select(Article)
            .where(Article.status == "published")
            .where(Article.category_id == article.category_id)
            .where(Article.id != article.id)
            .order_by(desc(Article.published_at))
            .limit(4)
        ).scalars().all()

    # Fetch categories for nav
    categories = db.execute(
        select(Category)
        .where(Category.is_active == True)
        .order_by(Category.display_order)
    ).scalars().all()

    return request.app.state.templates.TemplateResponse("article.html", {
        "request": request,
        "article": article,
        "related": related,
        "categories": categories,
    })


# === Category page ===
@router.get("/categoria/{slug}", response_class=HTMLResponse)
async def category_page(
    request: Request,
    slug: str,
    page: int = Query(1, ge=1),
):
    db: Session = next(get_db())

    category = db.execute(
        select(Category).where(Category.slug == slug)
    ).scalars().first()

    if not category:
        raise HTTPException(status_code=404, detail="Categoría no encontrada")

    per_page = 12
    offset = (page - 1) * per_page

    total = db.execute(
        select(func.count(Article.id))
        .where(Article.status == "published")
        .where(Article.category_id == category.id)
    ).scalar()

    articles = db.execute(
        select(Article)
        .where(Article.status == "published")
        .where(Article.category_id == category.id)
        .order_by(desc(Article.published_at))
        .offset(offset)
        .limit(per_page)
    ).scalars().all()

    categories = db.execute(
        select(Category)
        .where(Category.is_active == True)
        .order_by(Category.display_order)
    ).scalars().all()

    total_pages = (total + per_page - 1) // per_page if total > 0 else 1

    return request.app.state.templates.TemplateResponse("category.html", {
        "request": request,
        "category": category,
        "articles": articles,
        "categories": categories,
        "page": page,
        "total_pages": total_pages,
    })


# === Search ===
@router.get("/buscar", response_class=HTMLResponse)
async def search(
    request: Request,
    q: str = Query(..., min_length=1),
    page: int = Query(1, ge=1),
):
    db: Session = next(get_db())

    per_page = 10
    offset = (page - 1) * per_page

    # SQLite FTS or LIKE search
    search_term = f"%{q}%"
    query = (
        select(Article)
        .where(Article.status == "published")
        .where(
            (Article.title.like(search_term)) |
            (Article.body_markdown.like(search_term)) |
            (Article.excerpt.like(search_term))
        )
        .order_by(desc(Article.published_at))
    )

    total = db.execute(
        select(func.count()).select_from(query.subquery())
    ).scalar()

    articles = db.execute(query.offset(offset).limit(per_page)).scalars().all()

    categories = db.execute(
        select(Category)
        .where(Category.is_active == True)
        .order_by(Category.display_order)
    ).scalars().all()

    total_pages = (total + per_page - 1) // per_page if total > 0 else 1

    return request.app.state.templates.TemplateResponse("search.html", {
        "request": request,
        "query": q,
        "articles": articles,
        "categories": categories,
        "page": page,
        "total_pages": total_pages,
        "total_results": total,
    })


# === RSS Feed ===
@router.get("/feed.xml")
async def rss_feed():
    db: Session = next(get_db())

    articles = db.execute(
        select(Article)
        .where(Article.status == "published")
        .order_by(desc(Article.published_at))
        .limit(20)
    ).scalars().all()

    items = []
    for a in articles:
        items.append(f"""
        <item>
            <title>{_xml_escape(a.title)}</title>
            <link>https://latinos.org/articulo/{a.slug}</link>
            <guid>https://latinos.org/articulo/{a.slug}</guid>
            <pubDate>{a.published_at.strftime('%a, %d %b %Y %H:%M:%S GMT') if a.published_at else ''}</pubDate>
            <description>{_xml_escape(a.excerpt or a.meta_description or '')}</description>
        </item>""")

    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
    <title>Latinos.org</title>
    <link>https://latinos.org</link>
    <description>Noticias, cultura y entretenimiento para la comunidad Hispana/Latina</description>
    <language>es</language>
    {''.join(items)}
</channel>
</rss>"""

    return Response(content=rss, media_type="application/rss+xml")


# === Sitemap ===
@router.get("/sitemap.xml")
async def sitemap():
    db: Session = next(get_db())

    articles = db.execute(
        select(Article.slug, Article.published_at)
        .where(Article.status == "published")
        .order_by(desc(Article.published_at))
        .limit(1000)
    ).all()

    categories = db.execute(
        select(Category.slug).where(Category.is_active == True)
    ).all()

    urls = ["https://latinos.org/"]
    for slug, _ in articles:
        urls.append(f"https://latinos.org/articulo/{slug}")
    for (slug,) in categories:
        urls.append(f"https://latinos.org/categoria/{slug}")

    xml_parts = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml_parts.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    for url in urls:
        xml_parts.append(f"<url><loc>{url}</loc></url>")
    xml_parts.append('</urlset>')

    return Response(content="\n".join(xml_parts), media_type="application/xml")


# === Robots.txt ===
@router.get("/robots.txt")
async def robots():
    content = "User-agent: *\nAllow: /\nSitemap: https://latinos.org/sitemap.xml\n"
    return Response(content=content, media_type="text/plain")


def _xml_escape(text: str) -> str:
    """Escape XML special characters."""
    if not text:
        return ""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
