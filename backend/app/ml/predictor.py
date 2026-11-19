"""Model loading + inference. Everything here degrades gracefully: if no artifact exists or inference
fails, callers get `None` and use the labelled non-ML fallback."""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from ..config import get_settings
from .features import DEMAND_FEATURES, WAIT_FEATURES

log = logging.getLogger("queueless.ml")
_lock = threading.Lock()
_cache: dict[str, object] = {}


@dataclass
class WaitPrediction:
    minutes: float
    lower: float
    upper: float
    model_version: str
    trained_on: str      # "synthetic" until a model is retrained on real data


def _model_dir() -> Path:
    return Path(get_settings().model_dir)


def _load(name: str):
    path = _model_dir() / f"{name}.joblib"
    if not get_settings().ml_enabled or not path.exists():
        return None
    with _lock:
        if name not in _cache:
            try:
                _cache[name] = joblib.load(path)
                log.info("loaded model %s", path)
            except Exception:  # corrupted / incompatible artifact must never break queue operations
                log.exception("could not load model %s", path)
                _cache[name] = None
        return _cache[name]


def reload_models() -> None:
    with _lock:
        _cache.clear()


def wait_model_info() -> dict | None:
    b = _load("wait_time_latest")
    if not b:
        return None
    return {k: b[k] for k in ("version", "algorithm", "trained_on", "metrics", "trained_at", "interval_nominal_coverage") if k in b}


def predict_wait_batch(rows: list[dict]) -> list[WaitPrediction] | None:
    """One vectorised call for a whole queue. Returns None if ML is unavailable or fails (caller uses the fallback)."""
    bundle = _load("wait_time_latest")
    if not bundle or not rows:
        return None if not bundle else []
    try:
        frame = pd.DataFrame([{c: r[c] for c in WAIT_FEATURES} for r in rows])
        points = np.clip(bundle["model"].predict(frame), 0, None)
        edges, lo, hi = bundle["interval_edges"], bundle["interval_lo"], bundle["interval_hi"]
        out = []
        for point in points:
            b = min(int(np.searchsorted(edges, point, side="right")), len(lo) - 1)
            out.append(WaitPrediction(round(float(point), 1), round(float(max(0.0, point + lo[b])), 1),
                                      round(float(point + hi[b]), 1), bundle["version"], bundle.get("trained_on", "synthetic")))
        return out
    except Exception:
        log.exception("wait-time inference failed; falling back")
        return None


def predict_wait(features: dict) -> WaitPrediction | None:
    res = predict_wait_batch([features])
    return res[0] if res else None


def predict_demand(horizon: int, features: dict) -> tuple[float, str] | None:
    bundle = _load("demand_latest")
    if not bundle or horizon not in bundle["models"]:
        return None
    try:
        row = pd.DataFrame([{c: features[c] for c in DEMAND_FEATURES}])
        return float(max(0.0, bundle["models"][horizon].predict(row)[0])), bundle["version"]
    except Exception:
        log.exception("demand inference failed; falling back")
        return None


def demand_model_info() -> dict | None:
    b = _load("demand_latest")
    if not b:
        return None
    return {k: b[k] for k in ("version", "algorithms", "trained_on", "metrics", "trained_at") if k in b}


def registry() -> list[dict]:
    p = _model_dir() / "registry.json"
    return json.loads(p.read_text()) if p.exists() else []
