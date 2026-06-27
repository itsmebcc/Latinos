"""
Shared database access for the pipeline.
Points at the same SQLite DB used by the website.
"""

import sys
from pathlib import Path

# Add website module to path so we share models
WEBSITE_DIR = Path(__file__).parent.parent / "website"
sys.path.insert(0, str(WEBSITE_DIR))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from models import Base, Category, Source, RawArticle, Article, PipelineRun
from database import DB_PATH

# Pipeline uses the SAME database as the website
PIPELINE_DB_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    PIPELINE_DB_URL,
    connect_args={"check_same_thread": False, "timeout": 30},
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Initialize database tables."""
    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
        conn.execute(text("PRAGMA foreign_keys=ON"))
    Base.metadata.create_all(engine)
    print(f"[Pipeline DB] Connected to {DB_PATH}")


def get_session():
    """Get a database session."""
    return SessionLocal()
