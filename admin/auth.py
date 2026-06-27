"""
Latinos.org — Admin Portal Authentication.
Simple session-based auth with a single admin password.
"""

import os
import hmac
import secrets
from datetime import datetime, timedelta
from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse

# Admin password — set via env var or default for local dev
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "latinos2026")

# Session duration
SESSION_DURATION = timedelta(hours=12)

# In-memory session store (fine for single-user admin)
_active_sessions: dict[str, datetime] = {}


def create_session() -> str:
    """Create a new session token."""
    token = secrets.token_urlsafe(32)
    _active_sessions[token] = datetime.utcnow() + SESSION_DURATION
    return token


def verify_session(token: str | None) -> bool:
    """Check if a session token is valid."""
    if not token:
        return False
    expiry = _active_sessions.get(token)
    if not expiry:
        return False
    if datetime.utcnow() > expiry:
        del _active_sessions[token]
        return False
    return True


def destroy_session(token: str):
    """Destroy a session."""
    _active_sessions.pop(token, None)


def get_session_token(request: Request) -> str | None:
    """Extract session token from cookie."""
    return request.cookies.get("latinos_admin_session")


def require_auth(request: Request):
    """Dependency: redirect to login if not authenticated."""
    token = get_session_token(request)
    if not verify_session(token):
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return token


def check_auth(request: Request) -> bool:
    """Non-raising auth check for templates."""
    return verify_session(get_session_token(request))


def verify_password(password: str) -> bool:
    """Check password against configured admin password."""
    return hmac.compare_digest(password, ADMIN_PASSWORD)
