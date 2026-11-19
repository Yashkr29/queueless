"""Phase-2 retraining on REAL operational data (threshold-based, never per transaction).

    python ml/retrain_wait_time.py [--min-rows 2000] [--promote]

1. Export real rows: first stored prediction's feature snapshot x the measured wait (service_records), is_demo = false.
2. Gate: refuse to train below --min-rows.
3. Chronological 70/15/15 split, benchmark the candidates from train_wait_time.py, pick on validation MAE.
4. Compare the candidate with the CURRENT model on the same untouched test rows.
5. Only with --promote AND a lower test MAE: write wait_time_latest.joblib (trained_on = "real") and append to registry.json.
   Every earlier version file is kept, so roll-back = copy an old versioned file over wait_time_latest.joblib.
"""
import argparse

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import select

from common import MODEL_DIR, append_registry, utc_stamp  # noqa: E402  (sets sys.path)
from train_wait_time import candidates, metrics  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.ml.features import WAIT_FEATURES, WAIT_TARGET  # noqa: E402
from app.models import Prediction, QueueToken, ServiceRecord  # noqa: E402


def export_real() -> pd.DataFrame:
    with SessionLocal() as db:
        rows = db.execute(select(ServiceRecord.token_id, ServiceRecord.service_start_time, ServiceRecord.actual_wait_minutes)
                          .join(QueueToken, QueueToken.token_id == ServiceRecord.token_id)
                          .where(QueueToken.is_demo.is_(False), ServiceRecord.actual_wait_minutes.is_not(None))).all()
        first = {}
        for p in db.scalars(select(Prediction).where(Prediction.features.is_not(None)).order_by(Prediction.prediction_id)):
            first.setdefault(p.token_id, p.features)
    recs = [{**first[t], WAIT_TARGET: float(w), "date": s.date(), "token_id": t} for t, s, w in rows if t in first]
    return pd.DataFrame(recs)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-rows", type=int, default=2000)
    ap.add_argument("--promote", action="store_true")
    args = ap.parse_args()

    df = export_real()
    print(f"real labelled rows: {len(df):,} (need {args.min_rows:,})")
    if len(df) < args.min_rows:
        raise SystemExit("Not enough real data yet — keep the current model. Nothing changed.")
    df = df.drop_duplicates("token_id").dropna(subset=WAIT_FEATURES + [WAIT_TARGET])
    df = df[(df[WAIT_TARGET] >= 0) & (df[WAIT_TARGET] <= 240)]
    dates = sorted(df["date"].unique())
    c1, c2 = dates[int(len(dates) * 0.70)], dates[int(len(dates) * 0.85)]
    tr, va, te = df[df["date"] < c1], df[(df["date"] >= c1) & (df["date"] < c2)], df[df["date"] >= c2]
    y_tr = tr[WAIT_TARGET].clip(upper=tr[WAIT_TARGET].quantile(0.995))

    best = None
    for name, params, make in candidates(42):
        pipe = make().fit(tr[WAIT_FEATURES], y_tr)
        mae = metrics(va[WAIT_TARGET], pipe.predict(va[WAIT_FEATURES]))["MAE"]
        if best is None or mae < best[0]:
            best = (mae, name, params, pipe)
    _, name, params, pipe = best
    cand_test = metrics(te[WAIT_TARGET], pipe.predict(te[WAIT_FEATURES]))

    current = joblib.load(MODEL_DIR / "wait_time_latest.joblib") if (MODEL_DIR / "wait_time_latest.joblib").exists() else None
    cur_test = metrics(te[WAIT_TARGET], np.clip(current["model"].predict(te[WAIT_FEATURES]), 0, None)) if current else None
    print(f"candidate {name} {params}: test MAE {cand_test['MAE']:.2f}" + (f" | current model: {cur_test['MAE']:.2f}" if cur_test else ""))

    better = cur_test is None or cand_test["MAE"] < cur_test["MAE"]
    if not (args.promote and better):
        print("Not promoted." + ("" if better else " Candidate is not better than the current model.") + ("" if args.promote else " (dry run; pass --promote)"))
        return

    pv = np.clip(pipe.predict(va[WAIT_FEATURES]), 0, None)
    resid = va[WAIT_TARGET].to_numpy() - pv
    edges = np.quantile(pv, [0.25, 0.5, 0.75]); bins = np.searchsorted(edges, pv, side="right")
    lo = [float(np.quantile(resid[bins == b], 0.10)) if (bins == b).any() else -3.0 for b in range(4)]
    hi = [float(np.quantile(resid[bins == b], 0.90)) if (bins == b).any() else 3.0 for b in range(4)]
    version = f"wait-{name.lower()}-real-{utc_stamp()}"
    bundle = {"model": pipe, "version": version, "algorithm": name, "params": params, "features": WAIT_FEATURES, "trained_on": "real",
              "trained_at": utc_stamp(), "interval_edges": edges.tolist(), "interval_lo": lo, "interval_hi": hi, "interval_nominal_coverage": 0.8,
              "metrics": {"val": {}, "test": cand_test}, "data": {"rows": len(df), "split_cutoffs": [str(c1), str(c2)]}}
    joblib.dump(bundle, MODEL_DIR / f"{version}.joblib")
    joblib.dump(bundle, MODEL_DIR / "wait_time_latest.joblib")
    append_registry({"model": "wait_time", "version": version, "algorithm": name, "trained_on": "real", "metrics": bundle["metrics"],
                     "data": bundle["data"], "trained_at": bundle["trained_at"], "note": "Retrained on real operational data."})
    print(f"promoted {version}. Restart the API (or call predictor.reload_models()) to load it.")


if __name__ == "__main__":
    main()
