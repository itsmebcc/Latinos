"""
Latinos.org — Database connection and helpers.
Supports both local pipeline (read/write) and public site (read-only).
"""

import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# === Database path ===
# On Railway: use DATA_DIR env var or default to the website data directory
# Locally: same file is used by pipeline, admin, and website
DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).parent / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "latinos.db"

# SQLite connection — enable WAL mode for better concurrent read performance
DB_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DB_URL,
    connect_args={"check_same_thread": False, "timeout": 30},
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """FastAPI dependency: yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database — create tables if they don't exist."""
    from models import Base
    # Enable WAL mode for better concurrent access
    with engine.connect() as conn:
        from sqlalchemy import text
        conn.execute(text("PRAGMA journal_mode=WAL"))
        conn.execute(text("PRAGMA foreign_keys=ON"))
    Base.metadata.create_all(engine)
    print(f"[DB] Initialized at {DB_PATH}")
