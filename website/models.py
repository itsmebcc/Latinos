"""
Latinos.org — Shared database models (SQLite)
Used by both the local pipeline/admin AND the public website (read-only).
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, Text, String, DateTime, Boolean, Float, ForeignKey, Index
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Category(Base):
    """Content vertical (Noticias, Deportes, Entretenimiento, etc.)"""
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    name_en = Column(String(200))  # English display name
    description = Column(Text)
    display_order = Column(Integer, default=99)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    articles = relationship("Article", back_populates="category_rel")


class Source(Base):
    """An inspiration site or content source."""
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)  # e.g., "Univision"
    domain = Column(String(200), unique=True, nullable=False)  # univision.com
    site_type = Column(String(50))  # news, sports, culture, entertainment
    rss_url = Column(Text)  # Primary RSS feed if available
    scrape_config = Column(Text)  # JSON config for CloakBrowser scraper
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    raw_articles = relationship("RawArticle", back_populates="source_rel")


class RawArticle(Base):
    """Raw scraped content from inspiration sites — pre-LLM processing."""
    __tablename__ = "raw_articles"

    id = Column(Integer, primary_key=True)
    source_id = Column(Integer, ForeignKey("sources.id"), nullable=False)
    source_url = Column(Text, unique=True, nullable=False)
    url_hash = Column(String(64), unique=True, index=True)  # SHA256 for dedup
    title = Column(Text)
    author = Column(String(500))
    publish_date = Column(DateTime)
    raw_html = Column(Text)
    extracted_text = Column(Text)
    image_urls = Column(Text)  # JSON array
    category_hint = Column(String(100))
    discovered_at = Column(DateTime, default=datetime.utcnow)

    # Pipeline status tracking
    status = Column(String(30), default="discovered", index=True)
    # discovered → processing → rewritten → approved → published → rejected
    error_message = Column(Text)
    processed_at = Column(DateTime)

    source_rel = relationship("Source", back_populates="raw_articles")
    articles = relationship("Article", back_populates="raw_article_rel")


class Article(Base):
    """A fully processed, ready-to-publish (or published) article."""
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True)
    raw_article_id = Column(Integer, ForeignKey("raw_articles.id"), nullable=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)

    # Content (Spanish — primary language)
    title = Column(Text, nullable=False)
    slug = Column(String(300), unique=True, nullable=False, index=True)
    body_markdown = Column(Text, nullable=False)
    body_html = Column(Text)
    excerpt = Column(Text)

    # English version
    title_en = Column(Text)
    body_markdown_en = Column(Text)
    body_html_en = Column(Text)
    excerpt_en = Column(Text)

    # Metadata
    meta_description = Column(String(200))
    tags = Column(Text)  # JSON array
    language = Column(String(10), default="es")  # es, en, bilingual
    author_display = Column(String(200), default="Latinos.org")
    source_credit = Column(String(500))  # Attribution to original source

    # Media
    image_url = Column(Text)  # Relative path: /static/images/articles/xxx.webp
    image_alt = Column(Text)
    image_credit = Column(String(500))

    # Pipeline
    quality_score = Column(Float, default=0.0)  # 0.0 to 1.0 from LLM QA step
    content_type = Column(String(50), default="news")  # news, opinion, listicle, feature

    # Lifecycle
    status = Column(String(30), default="draft", index=True)
    # draft → pending_review → approved → scheduled → published → rejected
    created_at = Column(DateTime, default=datetime.utcnow)
    approved_at = Column(DateTime)
    published_at = Column(DateTime, index=True)
    scheduled_for = Column(DateTime)

    # Analytics
    view_count = Column(Integer, default=0)

    # Flags
    is_breaking = Column(Boolean, default=False)
    is_featured = Column(Boolean, default=False)

    category_rel = relationship("Category", back_populates="articles")
    raw_article_rel = relationship("RawArticle", back_populates="articles")


class PipelineRun(Base):
    """Track pipeline execution for monitoring/debugging."""
    __tablename__ = "pipeline_runs"

    id = Column(Integer, primary_key=True)
    run_type = Column(String(50))  # scrape_rss, scrape_web, llm_rewrite, publish
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    articles_processed = Column(Integer, default=0)
    articles_succeeded = Column(Integer, default=0)
    articles_failed = Column(Integer, default=0)
    error_log = Column(Text)
    status = Column(String(30), default="running")  # running, completed, failed


# === Indexes for performance ===
Index("idx_articles_status_published", Article.status, Article.published_at)
Index("idx_articles_category_status", Article.category_id, Article.status)
Index("idx_raw_articles_status", RawArticle.status)
Index("idx_articles_slug", Article.slug)
Index("idx_articles_breaking", Article.is_breaking, Article.status)


def init_db(engine):
    """Create all tables."""
    Base.metadata.create_all(engine)
