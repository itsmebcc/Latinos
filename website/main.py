"""
Latinos.org — Public Website
FastAPI application serving the public-facing news site.
"""

import os
import sys
import json
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

# Ensure local imports work
BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

from database import init_db, engine
from routes import router


# === Lifespan: initialize DB on startup ===
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    print(f"[Latinos.org] Server started. DB: {engine.url}")
    yield
    print("[Latinos.org] Server shutting down.")


# === Create app ===
app = FastAPI(
    title="Latinos.org",
    description="Noticias, cultura y entretenimiento para la comunidad Hispana/Latina",
    version="1.0.0",
    lifespan=lifespan,
)

# === Templates ===
import markdown as md

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.filters["from_json"] = lambda s: json.loads(s) if s else []
templates.env.filters["to_json"] = lambda obj: json.dumps(obj, ensure_ascii=False)
templates.env.filters["markdown"] = lambda s: md.markdown(s, extensions=["extra", "nl2br"]) if s else ""
app.state.templates = templates

# === Static files ===
static_dir = BASE_DIR / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.middleware("http")
async def performance_headers(request: Request, call_next):
    """Cache static assets and add lightweight public-site security headers."""
    response = await call_next(request)

    if request.url.path.startswith("/static/"):
        response.headers.setdefault("Cache-Control", "public, max-age=31536000, immutable")
    elif request.url.path in {"/feed.xml", "/sitemap.xml", "/robots.txt"}:
        response.headers.setdefault("Cache-Control", "public, max-age=300")
    else:
        response.headers.setdefault("Cache-Control", "public, max-age=60")

    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return response

# === Routes ===
app.include_router(router)


# === Health check ===
@app.get("/health")
async def health():
    return {"status": "ok", "service": "latinos.org"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 9097))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
