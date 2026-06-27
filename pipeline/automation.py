"""
Latinos.org — Phase 7 local automation runner.

Provides a repeatable operator workflow for the local-only content machine:
health/status checks, scrape orchestration, optional LLM rewrite, optional
quality-threshold approval, publisher export, and optional Railway git push.

The Railway public app remains read-only. This module is intended to run on the
local content/admin machine.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

# Ensure pipeline modules win for `db`, while website modules remain importable.
PIPELINE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PIPELINE_DIR.parent
WEBSITE_DIR = PROJECT_ROOT / "website"
sys.path.insert(0, str(WEBSITE_DIR))
sys.path.insert(0, str(PIPELINE_DIR))

from config import CLOAKBROWSER_PATH, DB_PATH, VLLM_BASE_URL, VLLM_MODEL, load_sources  # noqa: E402
from db import get_session, init_db  # noqa: E402
from llm.client import check_health as check_vllm_health  # noqa: E402
from models import Article, PipelineRun, RawArticle, Source  # noqa: E402
from orchestrator import run_full_cycle, run_rss_only  # noqa: E402
from publisher import run_publish  # noqa: E402
from run_llm import run_llm_pipeline  # noqa: E402

RUNS_DIR = PIPELINE_DIR / "runs"
LATEST_REPORT_PATH = RUNS_DIR / "latest.json"


@dataclass
class StepResult:
    name: str
    status: str = "skipped"  # skipped, completed, failed
    message: str = ""
    count: int = 0
    duration_seconds: float = 0.0


@dataclass
class AutomationResult:
    started_at: str
    completed_at: Optional[str] = None
    status: str = "running"
    mode: str = "rss"
    dry_run: bool = True
    rewrite_limit: int = 0
    auto_approve_min_score: Optional[float] = None
    publish: bool = False
    push: bool = False
    health: dict[str, Any] = field(default_factory=dict)
    before_counts: dict[str, int] = field(default_factory=dict)
    after_counts: dict[str, int] = field(default_factory=dict)
    steps: list[StepResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    report_path: str = ""


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def git(args: list[str], check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=check,
    )


def db_counts() -> dict[str, int]:
    init_db(verbose=False)
    session = get_session()
    try:
        return {
            "sources": session.query(Source).count(),
            "raw_total": session.query(RawArticle).count(),
            "raw_discovered": session.query(RawArticle).filter(RawArticle.status == "discovered").count(),
            "raw_processing": session.query(RawArticle).filter(RawArticle.status == "processing").count(),
            "raw_rewritten": session.query(RawArticle).filter(RawArticle.status == "rewritten").count(),
            "articles_total": session.query(Article).count(),
            "pending_review": session.query(Article).filter(Article.status == "pending_review").count(),
            "approved": session.query(Article).filter(Article.status == "approved").count(),
            "published": session.query(Article).filter(Article.status == "published").count(),
            "rejected": session.query(Article).filter(Article.status == "rejected").count(),
        }
    finally:
        session.close()


async def collect_health(check_llm: bool = True) -> dict[str, Any]:
    config = load_sources()
    active_sources = [s for s in config.get("sources", []) if s.get("is_active")]
    rss_sources = [s for s in active_sources if s.get("ingestion_method") == "rss"]
    browser_sources = [s for s in active_sources if s.get("ingestion_method") == "browser"]
    git_status = git(["status", "--short"]).stdout.strip()

    health: dict[str, Any] = {
        "checked_at": utc_now(),
        "database_path": str(DB_PATH.relative_to(PROJECT_ROOT)),
        "database_exists": DB_PATH.exists(),
        "active_sources": len(active_sources),
        "rss_sources": len(rss_sources),
        "browser_sources": len(browser_sources),
        "cloakbrowser_path": str(CLOAKBROWSER_PATH),
        "cloakbrowser_exists": CLOAKBROWSER_PATH.exists(),
        "vllm_base_url": VLLM_BASE_URL,
        "vllm_model": VLLM_MODEL,
        "git_dirty": bool(git_status),
        "git_status_lines": git_status.splitlines()[:20] if git_status else [],
    }

    if check_llm:
        start = time.monotonic()
        healthy = await check_vllm_health()
        health["vllm_healthy"] = healthy
        health["vllm_check_seconds"] = round(time.monotonic() - start, 2)
    else:
        health["vllm_healthy"] = None
        health["vllm_check_seconds"] = 0

    return health


def auto_approve_articles(min_score: float, dry_run: bool) -> int:
    session = get_session()
    try:
        candidates = session.query(Article).filter(
            Article.status == "pending_review",
            Article.quality_score >= min_score,
        ).all()
        if dry_run:
            return len(candidates)

        now = datetime.utcnow()
        for article in candidates:
            article.status = "approved"
            article.approved_at = article.approved_at or now
        session.commit()
        return len(candidates)
    finally:
        session.close()


def write_report(result: AutomationResult) -> Path:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    report_path = RUNS_DIR / f"automation-{stamp}.json"
    result.report_path = str(report_path.relative_to(PROJECT_ROOT))
    payload = asdict(result)
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    LATEST_REPORT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return report_path


def load_latest_report() -> Optional[dict[str, Any]]:
    if not LATEST_REPORT_PATH.exists():
        return None
    try:
        return json.loads(LATEST_REPORT_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


async def run_automation(
    *,
    mode: str = "rss",
    dry_run: bool = True,
    rewrite_limit: int = 0,
    concurrency: int = 0,
    auto_approve_min_score: Optional[float] = None,
    publish: bool = False,
    push: bool = False,
    check_llm: bool = True,
) -> AutomationResult:
    """Run the local automation workflow and write a JSON report."""
    result = AutomationResult(
        started_at=utc_now(),
        mode=mode,
        dry_run=dry_run,
        rewrite_limit=rewrite_limit,
        auto_approve_min_score=auto_approve_min_score,
        publish=publish,
        push=push,
    )

    pipeline_run = None
    session = None
    try:
        result.before_counts = db_counts()
        result.health = await collect_health(check_llm=check_llm)

        if dry_run:
            result.steps.append(StepResult(
                name="plan",
                status="completed",
                message="Dry run only: no scraping, rewriting, approval, publishing, commit, or push performed.",
            ))
            if auto_approve_min_score is not None:
                count = auto_approve_articles(auto_approve_min_score, dry_run=True)
                result.steps.append(StepResult(
                    name="auto_approve_preview",
                    status="completed",
                    count=count,
                    message=f"Would approve pending_review articles with quality_score >= {auto_approve_min_score}.",
                ))
            result.status = "completed"
            return result

        session = get_session()
        pipeline_run = PipelineRun(run_type="automation", status="running", started_at=datetime.utcnow())
        session.add(pipeline_run)
        session.commit()

        if mode in {"rss", "full"}:
            start = time.monotonic()
            try:
                count = await (run_full_cycle() if mode == "full" else run_rss_only())
                result.steps.append(StepResult(
                    name="scrape",
                    status="completed",
                    count=count if isinstance(count, int) else 0,
                    duration_seconds=round(time.monotonic() - start, 2),
                    message=f"{mode} scrape completed.",
                ))
            except Exception as exc:
                msg = f"{type(exc).__name__}: {exc}"
                result.errors.append(f"scrape: {msg}")
                result.steps.append(StepResult("scrape", "failed", msg, duration_seconds=round(time.monotonic() - start, 2)))

        if rewrite_limit != 0:
            start = time.monotonic()
            if result.health.get("vllm_healthy") is False:
                msg = "Skipped LLM rewrite because vLLM health check failed."
                result.errors.append(msg)
                result.steps.append(StepResult("llm_rewrite", "skipped", msg))
            else:
                try:
                    saved = await run_llm_pipeline(limit=max(rewrite_limit, 0), concurrency=concurrency)
                    result.steps.append(StepResult(
                        name="llm_rewrite",
                        status="completed",
                        count=saved,
                        duration_seconds=round(time.monotonic() - start, 2),
                        message="LLM rewrite completed.",
                    ))
                except Exception as exc:
                    msg = f"{type(exc).__name__}: {exc}"
                    result.errors.append(f"llm_rewrite: {msg}")
                    result.steps.append(StepResult("llm_rewrite", "failed", msg, duration_seconds=round(time.monotonic() - start, 2)))
        else:
            result.steps.append(StepResult("llm_rewrite", "skipped", "rewrite_limit=0"))

        if auto_approve_min_score is not None:
            start = time.monotonic()
            count = auto_approve_articles(auto_approve_min_score, dry_run=False)
            result.steps.append(StepResult(
                name="auto_approve",
                status="completed",
                count=count,
                duration_seconds=round(time.monotonic() - start, 2),
                message=f"Approved pending_review articles with quality_score >= {auto_approve_min_score}.",
            ))

        if publish:
            start = time.monotonic()
            try:
                publish_result = run_publish(download_images=True, commit=True, push=push)
                result.steps.append(StepResult(
                    name="publish",
                    status="completed",
                    count=publish_result.articles_processed,
                    duration_seconds=round(time.monotonic() - start, 2),
                    message=publish_result.message,
                ))
            except Exception as exc:
                msg = f"{type(exc).__name__}: {exc}"
                result.errors.append(f"publish: {msg}")
                result.steps.append(StepResult("publish", "failed", msg, duration_seconds=round(time.monotonic() - start, 2)))
        else:
            result.steps.append(StepResult("publish", "skipped", "publish=False"))

        result.status = "completed" if not result.errors else "completed_with_errors"
        return result

    except Exception as exc:
        result.status = "failed"
        result.errors.append(f"automation: {type(exc).__name__}: {exc}")
        return result
    finally:
        result.completed_at = utc_now()
        try:
            result.after_counts = db_counts()
        except Exception as exc:
            result.errors.append(f"after_counts: {type(exc).__name__}: {exc}")

        if session and pipeline_run:
            try:
                pipeline_run.status = "completed" if result.status == "completed" else result.status
                pipeline_run.completed_at = datetime.utcnow()
                pipeline_run.articles_processed = result.after_counts.get("raw_total", 0) - result.before_counts.get("raw_total", 0)
                pipeline_run.articles_succeeded = result.after_counts.get("published", 0) - result.before_counts.get("published", 0)
                pipeline_run.articles_failed = len(result.errors)
                pipeline_run.error_log = "\n".join(result.errors) if result.errors else None
                session.commit()
            except Exception:
                session.rollback()
            finally:
                session.close()

        write_report(result)


async def status_payload(check_llm: bool = False) -> dict[str, Any]:
    return {
        "ok": True,
        "health": await collect_health(check_llm=check_llm),
        "counts": db_counts(),
        "latest_report": load_latest_report(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Latinos.org Phase 7 automation runner")
    parser.add_argument("--mode", choices=["rss", "full", "none"], default="rss", help="Scrape mode before rewrite/publish")
    parser.add_argument("--dry-run", action="store_true", help="Plan/check only; do not mutate DB or git")
    parser.add_argument("--run", action="store_true", help="Actually run mutating workflow (default is dry-run for safety)")
    parser.add_argument("--rewrite-limit", type=int, default=0, help="Number of discovered raw articles to rewrite; 0 skips LLM")
    parser.add_argument("--concurrency", type=int, default=0, help="LLM concurrency override")
    parser.add_argument("--auto-approve-min-score", type=float, default=None, help="Approve pending_review articles at/above this quality score")
    parser.add_argument("--publish", action="store_true", help="Run publisher after optional approval")
    parser.add_argument("--push", action="store_true", help="Push deployable publisher commit to GitHub/Railway")
    parser.add_argument("--health", action="store_true", help="Print health/status only")
    parser.add_argument("--no-llm-health", action="store_true", help="Skip vLLM health check")
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    args = parser.parse_args()

    if args.health:
        payload = asyncio.run(status_payload(check_llm=not args.no_llm_health))
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload)
        return

    dry_run = args.dry_run or not args.run
    result = asyncio.run(run_automation(
        mode=args.mode,
        dry_run=dry_run,
        rewrite_limit=args.rewrite_limit,
        concurrency=args.concurrency,
        auto_approve_min_score=args.auto_approve_min_score,
        publish=args.publish,
        push=args.push,
        check_llm=not args.no_llm_health,
    ))

    if args.json:
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    else:
        print("=== Latinos.org Automation ===")
        print(f"Status: {result.status}")
        print(f"Mode: {result.mode} | Dry run: {result.dry_run}")
        print(f"Report: {result.report_path}")
        for step in result.steps:
            print(f"- {step.name}: {step.status} ({step.count}) {step.message}")
        if result.errors:
            print("Errors:")
            for err in result.errors:
                print(f"  - {err}")


if __name__ == "__main__":
    main()
