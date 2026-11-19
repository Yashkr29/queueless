"""Model 2 — customer demand forecasting (30 / 60 / 120 minutes ahead), per service.

    python ml/train_demand.py [--days 168] [--seed 7]

Benchmarks seasonal-naive + historical-mean baselines against RandomForest, GradientBoosting and XGBoost,
selects per horizon on validation MAE (chronological split), reports MAE / RMSE / WAPE on the test split.
Prophet is an optional extra candidate and is not installed by default. SIMULATED data only.
"""
import argparse
import json
from datetime import timedelta

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from xgboost import XGBRegressor

from common import MODEL_DIR, REPORT_DIR, append_registry, utc_stamp  # noqa: E402
from app.ml.features import DEMAND_BIN_MINUTES, DEMAND_FEATURES, DEMAND_HORIZONS, demand_feature_row, wape  # noqa: E402
from app.ml.simulation import SERVICES, SimConfig, simulate  # noqa: E402

BINS_PER_DAY = 24 * 60 // DEMAND_BIN_MINUTES
NUMERIC = [f for f in DEMAND_FEATURES if f != "service_type"]


def pipe(est):
    return Pipeline([("pre", ColumnTransformer([("cat", OneHotEncoder(handle_unknown="ignore"), ["service_type"]),
                                                  ("num", "passthrough", NUMERIC)])), ("model", est)])


def build_rows(sim, cfg):
    df = sim.tokens
    n_bins = (cfg.days + 1) * BINS_PER_DAY
    events, holidays = set(sim.event_dates), set(sim.holiday_dates)
    rows = []
    for svc in SERVICES:
        sid = svc["service_id"]
        counts = np.zeros(n_bins, dtype=int)
        d = df[df["service_id"] == sid]
        idx = ((pd.to_datetime(d["entered_at"]).dt.normalize() - pd.Timestamp(cfg.start_date)).dt.days * BINS_PER_DAY
               + (pd.to_datetime(d["entered_at"]).dt.hour * 60 + pd.to_datetime(d["entered_at"]).dt.minute) // DEMAND_BIN_MINUTES)
        np.add.at(counts, idx.to_numpy(), 1)
        get = lambda i, c=counts: int(c[i]) if 0 <= i < len(c) else 0
        for day in range(28, cfg.days):                      # first 4 weeks lack history for lag features
            date_ = cfg.start_date + timedelta(days=day)
            if date_.weekday() == 6:
                continue
            for b in range(cfg.open_hour * 2, cfg.close_hour * 2):
                i = day * BINS_PER_DAY + b
                for h in DEMAND_HORIZONS:
                    hb = h // DEMAND_BIN_MINUTES
                    f = demand_feature_row(get_count=get, bin_index=i, horizon_bins=hb, hour_of_day=b / 2, day_of_week=date_.weekday(),
                                           is_holiday=int(date_ in holidays), special_event=int(date_ in events), service_type=sid)
                    f.update(date=date_, horizon=h, target=sum(get(i + k) for k in range(hb)))
                    rows.append(f)
    return pd.DataFrame(rows)


def m(y, p):
    return {"MAE": float(mean_absolute_error(y, p)), "RMSE": float(np.sqrt(mean_squared_error(y, p))), "WAPE": float(wape(y, p))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=168)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    cfg = SimConfig(days=args.days, seed=args.seed)
    sim = simulate(cfg)
    data = build_rows(sim, cfg)
    print(f"{len(data):,} forecast rows from {len(sim.tokens):,} simulated arrivals")

    dates = sorted(data["date"].unique())
    c1, c2 = dates[int(len(dates) * 0.70)], dates[int(len(dates) * 0.85)]
    bundle_models, bundle_algos, report, md = {}, {}, {}, [
        "# Demand-forecast model report\n", "> **SIMULATED data.** Not evidence of real-world accuracy.\n",
        f"Chronological split by date: train < {c1} <= val < {c2} <= test. First 28 days dropped (lag features need history). "
        "Prophet was not benchmarked (optional dependency).\n"]
    for h in DEMAND_HORIZONS:
        d = data[data["horizon"] == h]
        tr, va, te = d[d["date"] < c1], d[(d["date"] >= c1) & (d["date"] < c2)], d[d["date"] >= c2]
        res = {"Seasonal naive (same window last week)": (m(va["target"], va["prev_week_same"]), m(te["target"], te["prev_week_same"])),
               "Historical mean (4 weeks)": (m(va["target"], va["historical_demand"]), m(te["target"], te["historical_demand"]))}
        fitted = {}
        for name, est in {
            "RandomForest": RandomForestRegressor(n_estimators=300, min_samples_leaf=3, n_jobs=-1, random_state=1),
            "GradientBoosting": GradientBoostingRegressor(n_estimators=250, learning_rate=0.05, max_depth=3, subsample=0.8, random_state=1),
            "XGBoost": XGBRegressor(n_estimators=300, learning_rate=0.05, max_depth=4, subsample=0.8, n_jobs=4, random_state=1),
        }.items():
            p = pipe(est).fit(tr[DEMAND_FEATURES], tr["target"])
            fitted[name] = p
            res[name] = (m(va["target"], p.predict(va[DEMAND_FEATURES])), m(te["target"], p.predict(te[DEMAND_FEATURES])))
        winner = min(fitted, key=lambda k: res[k][0]["MAE"])
        bundle_models[h], bundle_algos[h] = fitted[winner], winner
        report[h] = {k: {"val": v[0], "test": v[1]} for k, v in res.items()} | {"selected": winner}
        print(f"horizon {h:3d} min -> {winner:16s} test MAE {res[winner][1]['MAE']:.2f}  WAPE {res[winner][1]['WAPE']:.1%}")
        md += [f"\n## Horizon {h} min — selected **{winner}**\n", "| Model | Val MAE | Test MAE | Test RMSE | Test WAPE |", "|---|---|---|---|---|"]
        md += [f"| {k} | {v[0]['MAE']:.2f} | {v[1]['MAE']:.2f} | {v[1]['RMSE']:.2f} | {v[1]['WAPE']:.1%} |" for k, v in sorted(res.items(), key=lambda kv: kv[1][0]["MAE"])]

    version = f"demand-{utc_stamp()}"
    bundle = {"models": bundle_models, "algorithms": bundle_algos, "version": version, "trained_on": "synthetic",
              "trained_at": utc_stamp(), "features": DEMAND_FEATURES,
              "metrics": {h: report[h][report[h]["selected"]]["test"] for h in DEMAND_HORIZONS}}
    joblib.dump(bundle, MODEL_DIR / f"{version}.joblib")
    joblib.dump(bundle, MODEL_DIR / "demand_latest.joblib")
    append_registry({"model": "demand", "version": version, "algorithms": bundle_algos, "trained_on": "synthetic",
                     "metrics": bundle["metrics"], "trained_at": bundle["trained_at"], "note": "SIMULATED-data metrics."})
    (REPORT_DIR / "demand_report.json").write_text(json.dumps(report, indent=2, default=str))
    (REPORT_DIR / "demand_report.md").write_text("\n".join(md), encoding="utf-8")
    print("report -> ml/reports/demand_report.md")


if __name__ == "__main__":
    main()
