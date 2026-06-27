"""
Pipeline configuration — loads sources.yaml and manages settings.
"""

import os
from pathlib import Path
from typing import Optional

import yaml

PIPELINE_DIR = Path(__file__).parent
PROJECT_ROOT = PIPELINE_DIR.parent

# === Database ===
# Use the same SQLite DB as the website
DB_PATH = PROJECT_ROOT / "website" / "data" / "latinos.db"

# === CloakBrowser ===
CLOAKBROWSER_PATH = Path(os.environ.get(
    "CLOAKBROWSER_PATH",
    "/home/user/browser-search"
))

# === vLLM ===
VLLM_BASE_URL = os.environ.get("VLLM_BASE_URL", "http://100.127.216.5:8000/v1")
VLLM_MODEL = os.environ.get("VLLM_MODEL", "qwen3.5-27b")
VLLM_API_KEY = os.environ.get("VLLM_API_KEY", "not-needed")  # vLLM doesn't require auth

# === Paths ===
IMAGES_DIR = PROJECT_ROOT / "website" / "static" / "images" / "articles"
PROMPTS_DIR = PIPELINE_DIR / "llm" / "prompts"

# === Concurrency ===
LLM_CONCURRENCY = int(os.environ.get("LLM_CONCURRENCY", "8"))


def load_sources() -> dict:
    """Load the sources configuration."""
    sources_path = PIPELINE_DIR / "scraper" / "sources.yaml"
    with open(sources_path, "r") as f:
        return yaml.safe_load(f)


def get_pipeline_config() -> dict:
    """Get the full pipeline config including sources and settings."""
    config = load_sources()
    return config


# Ensure directories exist
IMAGES_DIR.mkdir(parents=True, exist_ok=True)
PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
