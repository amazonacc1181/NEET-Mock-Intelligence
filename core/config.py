from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

# Runtime workspace can be redirected to persistent cloud storage (e.g. Google Drive
# from Colab) while the source code remains in the ephemeral notebook runtime.
WORKSPACE_DIR = Path(os.getenv("NEET_WORKSPACE_DIR", str(ROOT))).expanduser().resolve()
INPUT_DIR = WORKSPACE_DIR / "input"
MOCK_DIR = INPUT_DIR / "mock_papers"
SOLUTION_DIR = INPUT_DIR / "mock_solutions"
NEET_DIR = INPUT_DIR / "neet_2026"
DATA_DIR = Path(os.getenv("NEET_DATA_DIR", str(WORKSPACE_DIR / "data"))).expanduser().resolve()
PAGE_IMAGE_DIR = Path(os.getenv("NEET_PAGE_IMAGE_DIR", str(DATA_DIR / "page_images"))).expanduser().resolve()
CACHE_DIR = Path(os.getenv("NEET_CACHE_DIR", str(DATA_DIR / "cache"))).expanduser().resolve()
DB_PATH = Path(os.getenv("NEET_DB_PATH", str(DATA_DIR / "neet_matcher.sqlite3"))).expanduser().resolve()
DB_MIRROR_PATH = Path(os.getenv("NEET_DB_MIRROR_PATH", "")).expanduser().resolve() if os.getenv("NEET_DB_MIRROR_PATH") else None

for path in (MOCK_DIR, SOLUTION_DIR, NEET_DIR, DATA_DIR, PAGE_IMAGE_DIR, CACHE_DIR):
    path.mkdir(parents=True, exist_ok=True)

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://127.0.0.1:11434/v1").strip().rstrip("/")
LLM_API_KEY = os.getenv("LLM_API_KEY", "ollama").strip()
LLM_MODEL = os.getenv("LLM_MODEL", "qwen3.5:9b").strip()
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.1"))
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "180"))
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "5"))
LLM_BATCH_SIZE = int(os.getenv("LLM_BATCH_SIZE", "6"))

VERIFY_BASE_URL = os.getenv("VERIFY_BASE_URL", "").strip().rstrip("/") or LLM_BASE_URL
VERIFY_API_KEY = os.getenv("VERIFY_API_KEY", "").strip()
VERIFY_MODEL = os.getenv("VERIFY_MODEL", "").strip()

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3").strip()
ENABLE_EMBEDDINGS = os.getenv("ENABLE_EMBEDDINGS", "true").lower() in {"1", "true", "yes", "on"}
ENABLE_RERANKER = os.getenv("ENABLE_RERANKER", "false").lower() in {"1", "true", "yes", "on"}
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3").strip()
RERANK_CANDIDATES = max(50, min(250, int(os.getenv("RERANK_CANDIDATES", "150"))))
OCR_ENABLED = os.getenv("OCR_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
RENDER_PAGE_IMAGES = os.getenv("RENDER_PAGE_IMAGES", "true").lower() in {"1", "true", "yes", "on"}
TOP_CANDIDATES = max(10, min(60, int(os.getenv("TOP_CANDIDATES", "30"))))
MAX_MATCHES_PER_NEET_QUESTION = max(1, min(15, int(os.getenv("MAX_MATCHES_PER_NEET_QUESTION", "12"))))

EXPECTED_MOCK_QUESTIONS = int(os.getenv("EXPECTED_MOCK_QUESTIONS", "180"))
EXPECTED_NEET_QUESTIONS = int(os.getenv("EXPECTED_NEET_QUESTIONS", "180"))

VISION_BASE_URL = os.getenv("VISION_BASE_URL", "").strip().rstrip("/") or LLM_BASE_URL
VISION_API_KEY = os.getenv("VISION_API_KEY", "ollama").strip()
VISION_MODEL = os.getenv("VISION_MODEL", LLM_MODEL).strip()
VISION_MAX_IMAGES = max(0, min(12, int(os.getenv("VISION_MAX_IMAGES", "8"))))