from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent


def resolve_data_root() -> Path:
    configured = os.getenv("POEM_DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    if os.name == "nt":
        return Path("D:/poem_data")
    return PROJECT_ROOT / ".data"


DATA_ROOT = resolve_data_root()
CACHE_ROOT = DATA_ROOT / "cache"
TRANSLATION_CACHE_DIR = CACHE_ROOT / "translations"
TEXT_CACHE_DIR = CACHE_ROOT / "texts"
AUTO_SUPPLEMENT_CACHE_PATH = CACHE_ROOT / "auto_supplements.json"
EXPORT_ROOT = DATA_ROOT / "exports"
LOG_ROOT = DATA_ROOT / "logs"


def ensure_runtime_dirs() -> None:
    for path in (CACHE_ROOT, TRANSLATION_CACHE_DIR, TEXT_CACHE_DIR, EXPORT_ROOT, LOG_ROOT):
        path.mkdir(parents=True, exist_ok=True)
