"""
Latinos.org — Phase 8 analytics and growth reports.

Local-only reporting helper used by the admin portal and CLI. It summarizes
article performance, category coverage, newsletter signups, and share events
from the shared SQLite database.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

PIPELINE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PIPELINE_DIR.parent
WEBSITE_DIR = PROJECT_ROOT / "website"
sys.path.insert(0, str(WEBSITE_DIR))
sys.path.insert(0, str(PIPELINE_DIR))

from db import get_session, init_db  # noqa: E402
from models import Article, Category, NewsletterSignup, ShareEvent  # noqa: E402
from sqlalchemy import desc, func  # noqa: E402

REPORTS_DIR = PIPELINE_DIR / "reports"
LATEST_ANALYTICS_PATH = REPORTS_DIR / "latest_analytics.json"


@dataclass
class AnalyticsReport:
    generated_at: str
    days: int
    totals: dict[str, int]
    top_articles: list[dict[str, Any]]
    category_breakdown: list[dict[str, Any]]
    share_breakdown: list[dict[str, Any]]
    newsletter: dict[str, Any]
    recommendations: list[str]


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _article_dict(article: Article, shares: int = 0) -> dict[str, Any]:
    return {
        "id": article.id,
        "title": article.title,
        "slug": article.slug,
        "category": article.category_rel.name if article.category_rel else None,
        "published_at": article.published_at.isoformat() if article.published_at else None,
        "views": article.view_count or 0,
        "shares": shares,
        "quality_score": round(article.quality_score or 0, 3),
        "url": f"/articulo/{article.slug}",
    }


def generate_analytics_report(days: int = 30) -> AnalyticsReport:
    """Build a compact analytics report from the shared SQLite database."""
    init_db(verbose=False)
    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days)
    session = get_session()
    try:
        total_articles = session.query(Article).count()
        published = session.query(Article).filter(Article.status == "published").count()
        pending_review = session.query(Article).filter(Article.status == "pending_review").count()
        total_views = session.query(func.coalesce(func.sum(Article.view_count), 0)).scalar() or 0
        recent_signups = session.query(NewsletterSignup).filter(NewsletterSignup.created_at >= since).count()
        total_signups = session.query(NewsletterSignup).count()
        recent_shares = session.query(ShareEvent).filter(ShareEvent.created_at >= since).count()
        total_shares = session.query(ShareEvent).count()

        share_counts = dict(
            session.query(ShareEvent.article_id, func.count(ShareEvent.id))
            .group_by(ShareEvent.article_id)
            .all()
        )

        top_articles = [
            _article_dict(article, shares=share_counts.get(article.id, 0))
            for article in session.query(Article)
            .filter(Article.status == "published")
            .order_by(desc(Article.view_count), desc(Article.published_at))
            .limit(10)
            .all()
        ]

        category_rows = (
            session.query(
                Category.name,
                Category.slug,
                func.count(Article.id),
                func.coalesce(func.sum(Article.view_count), 0),
            )
            .outerjoin(Article, (Article.category_id == Category.id) & (Article.status == "published"))
            .filter(Category.is_active == True)
            .group_by(Category.id)
            .order_by(desc(func.coalesce(func.sum(Article.view_count), 0)))
            .all()
        )
        category_breakdown = [
            {"name": name, "slug": slug, "published": count, "views": int(views or 0)}
            for name, slug, count, views in category_rows
        ]

        share_rows = (
            session.query(ShareEvent.network, func.count(ShareEvent.id))
            .filter(ShareEvent.created_at >= since)
            .group_by(ShareEvent.network)
            .order_by(desc(func.count(ShareEvent.id)))
            .all()
        )
        share_breakdown = [{"network": network, "shares": count} for network, count in share_rows]

        recommendations: list[str] = []
        if pending_review:
            recommendations.append(f"Review queue has {pending_review} article(s); approve high-quality pieces before the next publish run.")
        if published and total_views == 0:
            recommendations.append("Published article view counts are still at zero; verify traffic and share distribution after deployment.")
        if recent_signups == 0:
            recommendations.append("No newsletter signups in the selected window; test the footer/article signup flow and promote it in high-traffic stories.")
        if top_articles:
            recommendations.append(f"Lead social/email promotion with the current top story: “{top_articles[0]['title']}”.")

        return AnalyticsReport(
            generated_at=utc_now(),
            days=days,
            totals={
                "articles": total_articles,
                "published": published,
                "pending_review": pending_review,
                "views": int(total_views),
                "shares": total_shares,
            },
            top_articles=top_articles,
            category_breakdown=category_breakdown,
            share_breakdown=share_breakdown,
            newsletter={
                "total_signups": total_signups,
                "recent_signups": recent_signups,
                "window_days": days,
            },
            recommendations=recommendations,
        )
    finally:
        session.close()


def write_report(report: AnalyticsReport) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    path = REPORTS_DIR / f"analytics-{stamp}.json"
    payload = json.dumps(asdict(report), ensure_ascii=False, indent=2)
    path.write_text(payload, encoding="utf-8")
    LATEST_ANALYTICS_PATH.write_text(payload, encoding="utf-8")
    return path


def load_latest_report() -> dict[str, Any] | None:
    if not LATEST_ANALYTICS_PATH.exists():
        return None
    try:
        return json.loads(LATEST_ANALYTICS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Latinos.org Phase 8 analytics report")
    parser.add_argument("--days", type=int, default=30, help="Rolling reporting window")
    parser.add_argument("--write", action="store_true", help="Write timestamped report under pipeline/reports/")
    parser.add_argument("--json", action="store_true", help="Print JSON")
    args = parser.parse_args()

    report = generate_analytics_report(days=args.days)
    path = write_report(report) if args.write else None
    payload = asdict(report)
    if path:
        payload["report_path"] = str(path.relative_to(PROJECT_ROOT))

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("=== Latinos.org Analytics ===")
        print(f"Generated: {report.generated_at} | Window: {report.days} days")
        print(f"Published: {report.totals['published']} | Views: {report.totals['views']} | Shares: {report.totals['shares']}")
        print(f"Newsletter signups: {report.newsletter['total_signups']} total / {report.newsletter['recent_signups']} recent")
        if path:
            print(f"Report: {path.relative_to(PROJECT_ROOT)}")
        for article in report.top_articles[:5]:
            print(f"- {article['views']} views · {article['shares']} shares · {article['title']}")


if __name__ == "__main__":
    main()
