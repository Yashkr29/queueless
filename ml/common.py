"""Shared helpers for the training scripts. Run scripts from the repo root:  python ml/train_wait_time.py"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))          # lets us import app.ml.* (single source of feature definitions)

MODEL_DIR = BACKEND / "models"
REPORT_DIR = ROOT / "ml" / "reports"
DATA_DIR = ROOT / "ml" / "data"
for d in (MODEL_DIR, REPORT_DIR, DATA_DIR):
    d.mkdir(parents=True, exist_ok=True)


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def append_registry(entry: dict) -> None:
    p = MODEL_DIR / "registry.json"
    reg = json.loads(p.read_text()) if p.exists() else []
    reg.append(entry)
    p.write_text(json.dumps(reg, indent=2, default=str))
