"""
Latinos.org — Admin Portal Application
Local-only admin interface for managing articles and pipeline.
"""

import os
import sys
import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse

# Setup paths — admin dir FIRST so admin routes.py takes priority over website routes.py
BASE_DIR = Path(__file__).parent
WEBSITE_DIR = BASE_DIR.parent / "website"
sys.path.insert(0, str(WEBSITE_DIR))  # website modules (db, models)
# Admin modules must be inserted AFTER website so they appear at position 0
sys.path.insert(0, str(BASE_DIR))

# Import admin-specific modules (must use explicit relative path to avoid collision)
import importlib
admin_routes = importlib.import_module("routes")
from database import init_db  # from website

app = FastAPI(
    title="Latinos.org Admin",
    description="Admin portal for article management",
    version="1.0.0",
)

# Templates
ADMIN_TEMPLATES = BASE_DIR / "templates"
templates = Jinja2Templates(directory=str(ADMIN_TEMPLATES))
templates.env.filters["from_json"] = lambda s: json.loads(s) if s else []
templates.env.filters["markdown"] = lambda s: s  # Raw markdown for editing
app.state.templates = templates

# Static files (share website static dir)
static_dir = WEBSITE_DIR / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Middleware to redirect unauthenticated requests
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Redirect to login for all non-public routes."""
    path = request.url.path
    public_paths = ["/login", "/logout", "/favicon.ico", "/static"]

    if any(path.startswith(p) for p in public_paths):
        return await call_next(request)

    # Check auth
    from auth import check_auth, get_session_token
    if not check_auth(request):
        if path.startswith("/api") or path.startswith("/bulk") or path.startswith("/publish"):
            from fastapi.responses import JSONResponse
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        return RedirectResponse("/login", status_code=303)

    return await call_next(request)

# Include routes
app.include_router(admin_routes.router)


@app.get("/")
async def root(request: Request):
    """Redirect to dashboard."""
    return RedirectResponse("/dashboard", status_code=303)


@app.on_event("startup")
async def startup():
    init_db()


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("ADMIN_PORT", 9098))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
