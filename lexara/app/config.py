"""Runtime configuration, read once at import time."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("LEXARA_DATA_DIR", BASE_DIR / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "lexara.db"

# Anthropic
MODEL = os.environ.get("LEXARA_MODEL", "claude-sonnet-4-6")
FAST_MODEL = os.environ.get("LEXARA_FAST_MODEL", "claude-haiku-4-5-20251001")
HAS_API_KEY = bool(os.environ.get("ANTHROPIC_API_KEY"))

# Limits
MAX_UPLOAD_BYTES = int(os.environ.get("LEXARA_MAX_UPLOAD_MB", "25")) * 1024 * 1024
MAX_DOC_CHARS = int(os.environ.get("LEXARA_MAX_DOC_CHARS", "400000"))
# How much of a document we hand to the model for a single review cell.
CELL_CONTEXT_CHARS = int(os.environ.get("LEXARA_CELL_CONTEXT_CHARS", "120000"))
REVIEW_WORKERS = int(os.environ.get("LEXARA_REVIEW_WORKERS", "6"))

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".markdown"}


def ensure_dirs() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
