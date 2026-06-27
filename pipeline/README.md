# Latinos.org Pipeline

Local-only content operations for Latinos.org. This directory is versioned for operator history but is not part of the Railway public app deploy root.

## Main Commands

### Scrape sources
```bash
python -m pipeline.orchestrator --mode rss
python -m pipeline.orchestrator --mode full
```

### Rewrite discovered raw articles with vLLM
```bash
python -m pipeline.run_llm --health
python -m pipeline.run_llm --limit 5 --concurrency 2
```

### Publish approved content and sync Railway artifacts
```bash
python -m pipeline.publisher --json
python -m pipeline.publisher --commit --json
python -m pipeline.publisher --push --json
```

## Phase 7 Automation Runner

`pipeline.automation` wraps the operational loop with health checks and JSON reports:

```bash
# Read-only health/status snapshot
python -m pipeline.automation --health --json

# Safe dry-run (default if --run is omitted)
python -m pipeline.automation --dry-run --mode rss --auto-approve-min-score 0.85 --json

# Mutating run: RSS scrape + publisher export, no LLM and no push
python -m pipeline.automation --run --mode rss --rewrite-limit 0 --publish --json

# Mutating run: RSS scrape + limited LLM rewrite + quality threshold approval + Railway push
python -m pipeline.automation --run --mode rss --rewrite-limit 5 --auto-approve-min-score 0.85 --publish --push
```

### Safety Defaults

- The automation CLI defaults to **dry-run** unless `--run` is explicitly passed.
- LLM rewriting is skipped unless `--rewrite-limit` is non-zero.
- Auto-approval is skipped unless `--auto-approve-min-score` is explicitly passed.
- Railway deployment is skipped unless both `--publish` and `--push` are passed.
- Reports are written to `pipeline/runs/latest.json` and timestamped files under `pipeline/runs/`.

### Admin Dashboard

The local admin dashboard exposes:

- `GET /automation/status` — DB/source/git status and latest automation report.
- `POST /automation/run` — dry-run or guarded mutating automation run.

Use the dashboard buttons for quick status checks and safe dry-runs; use the CLI for scheduled or long-running jobs.

## Phase 8 Analytics / Growth Reports

`pipeline.analytics` reads the shared SQLite database and summarizes content performance:

```bash
# Print report without writing files
python -m pipeline.analytics --days 30 --json

# Write timestamped local report and latest_analytics.json
python -m pipeline.analytics --days 30 --write --json
```

The local admin dashboard exposes:

- `GET /analytics` — visual analytics dashboard.
- `GET /analytics/report?days=30&write=true` — JSON report and optional local write.

Reports are written under `pipeline/reports/` and should stay local-only unless
you intentionally force-add a specific report for audit history.
