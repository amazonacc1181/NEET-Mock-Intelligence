from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

INPUT_DIR = ROOT / "input"
MOCK_DIR = INPUT_DIR / "mock_papers"
SOLUTION_DIR = INPUT_DIR / "mock_solutions"
NEET_DIR = INPUT_DIR / "neet_2026"
DATA_DIR = ROOT / "data"
PAGE_IMAGE_DIR = DATA_DIR / "page_images"
CACHE_DIR = DATA_DIR / "cache"
DB_PATH = DATA_DIR / "neet_matcher.sqlite3"

for path in (MOCK_DIR, SOLUTION_DIR, NEET_DIR, DATA_DIR, PAGE_IMAGE_DIR, CACHE_DIR):
    path.mkdir(parents=True, exist_ok=True)

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "").strip().rstrip("/")
LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip()
LLM_MODEL = os.getenv("LLM_MODEL", "").strip()
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.1"))
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "180"))
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "5"))
LLM_BATCH_SIZE = int(os.getenv("LLM_BATCH_SIZE", "6"))

VERIFY_BASE_URL = os.getenv("VERIFY_BASE_URL", "").strip().rstrip("/")
VERIFY_API_KEY = os.getenv("VERIFY_API_KEY", "").strip()
VERIFY_MODEL = os.getenv("VERIFY_MODEL", "").strip()

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5").strip()
ENABLE_EMBEDDINGS = os.getenv("ENABLE_EMBEDDINGS", "true").lower() in {"1", "true", "yes", "on"}
OCR_ENABLED = os.getenv("OCR_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
RENDER_PAGE_IMAGES = os.getenv("RENDER_PAGE_IMAGES", "true").lower() in {"1", "true", "yes", "on"}
TOP_CANDIDATES = max(10, min(60, int(os.getenv("TOP_CANDIDATES", "30"))))
MAX_MATCHES_PER_NEET_QUESTION = max(1, min(15, int(os.getenv("MAX_MATCHES_PER_NEET_QUESTION", "12"))))

EXPECTED_MOCK_QUESTIONS = int(os.getenv("EXPECTED_MOCK_QUESTIONS", "180"))
EXPECTED_NEET_QUESTIONS = int(os.getenv("EXPECTED_NEET_QUESTIONS", "180"))

VISION_BASE_URL = os.getenv("VISION_BASE_URL", "").strip().rstrip("/")
VISION_API_KEY = os.getenv("VISION_API_KEY", "").strip()
VISION_MODEL = os.getenv("VISION_MODEL", "").strip()
VISION_MAX_IMAGES = max(0, min(12, int(os.getenv("VISION_MAX_IMAGES", "8"))))