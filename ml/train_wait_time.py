"""Model 1 — waiting-time prediction: simulate -> clean -> chronological split -> benchmark -> calibrate -> save.

    python ml/train_wait_time.py [--days 140] [--seed 42]

Writes backend/models/wait_time_latest.joblib (+ versioned copy), registry.json and ml/reports/wait_time_report.{md,json,png}.
Every number produced here is measured on SIMULATED data.
"""
import argparse
import itertools
import json
import time

import joblib
import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from xgboost import XGBRegressor

from common import DATA_DIR, REPORT_DIR, MODEL_DIR, append_registry, utc_stamp  # noqa: E402  (sets sys.path)
from app.ml.features import CATEGORICAL, WAIT_FEATURES, WAIT_TARGET, fallback_wait_minutes  # noqa: E402
from app.ml.simulation import SimConfig, simulate  # noqa: E402

NUMERIC = [f for f in WAIT_FEATURES if f not in CATEGORICAL]


def make_pipeline(estimator, scale=False):
    num = StandardScaler() if scale else "passthrough"
    pre = ColumnTransformer([("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL), ("num", num, NUMERIC)])
    return Pipeline([("pre", pre), ("model", estimator)])


def candidates(seed):
    yield "LinearRegression", {}, lambda: make_pipeline(LinearRegression(), scale=True)
    for leaf in (5, 20):
        yield "RandomForest", {"min_samples_leaf": leaf}, (lambda leaf=leaf: make_pipeline(
            RandomForestRegressor(n_estimators=250, min_samples_leaf=leaf, n_jobs=-1, random_state=seed)))
    for loss, depth in itertools.product(("squared_error", "absolute_error"), (3, 4)):
        yield "GradientBoosting", {"loss": loss, "max_depth": depth}, (lambda loss=loss, depth=depth: make_pipeline(
            GradientBoostingRegressor(loss=loss, max_depth=depth, n_estimators=300, learning_rate=0.05, subsample=0.8, random_state=seed)))
    for obj, depth in itertools.product(("reg:squarederror", "reg:absoluteerror"), (4, 6)):
        yield "XGBoost", {"objective": obj, "max_depth": depth}, (lambda obj=obj, depth=depth: make_pipeline(
            XGBRegressor(objective=obj, max_depth=depth, n_estimators=300, learning_rate=0.05, subsample=0.8,
                         colsample_bytree=0.9, n_jobs=4, random_state=seed)))


def metrics(y, p):
    return {"MAE": float(mean_absolute_error(y, p)), "RMSE": float(np.sqrt(mean_squared_error(y, p))), "R2": float(r2_score(y, p))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=140)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    # ---------------------------------------------------------------- data
    t0 = time.time()
    sim = simulate(SimConfig(days=args.days, seed=args.seed))
    raw = sim.tokens
    raw.to_csv(DATA_DIR / "simulated_tokens.csv", index=False)
    print(f"simulated {len(raw):,} tokens in {time.time() - t0:.1f}s -> ml/data/simulated_tokens.csv")

    # ------------------------------------------------------------- cleaning
    df = raw[raw["outcome"] == "served"].copy()           # cancelled / no-show are censored: no wait label
    n0 = len(df)
    df = df.drop_duplicates(subset="token_id")
    df = df.dropna(subset=WAIT_FEATURES + [WAIT_TARGET])
    df = df[(df[WAIT_TARGET] >= 0) & (df[WAIT_TARGET] <= 240)]     # impossible waits (> 4h) are data errors
    print(f"cleaning: {n0:,} -> {len(df):,} rows")
    assert WAIT_TARGET not in WAIT_FEATURES and not {"outcome", "service_start", "called_at"} & set(WAIT_FEATURES), "target leakage"

    # ------------------------------------------------- chronological split
    dates = sorted(df["date"].unique())
    c1, c2 = dates[int(len(dates) * 0.70)], dates[int(len(dates) * 0.85)]
    train, val, test = df[df["date"] < c1], df[(df["date"] >= c1) & (df["date"] < c2)], df[df["date"] >= c2]
    print(f"split by date: train {len(train):,} (<{c1})  val {len(val):,}  test {len(test):,} (>={c2})")
    cap = train[WAIT_TARGET].quantile(0.995)               # winsorise TRAIN target only; evaluation stays untouched
    y_tr = train[WAIT_TARGET].clip(upper=cap)
    Xtr, Xva, Xte = train[WAIT_FEATURES], val[WAIT_FEATURES], test[WAIT_FEATURES]

    # ------------------------------------------------------------ benchmark
    rows, best = [], {}
    # The fallback is undefined when no eligible counter is open; compare on the rows where it is defined.
    mva, mte = (val["active_counters"] > 0).to_numpy(), (test["active_counters"] > 0).to_numpy()
    base_va = np.array([fallback_wait_minutes(r) or 0 for r in val[WAIT_FEATURES].to_dict("records")])
    base_te = np.array([fallback_wait_minutes(r) or 0 for r in test[WAIT_FEATURES].to_dict("records")])
    rows.append({"algorithm": "Fallback formula (non-ML, rows with an open counter)", "params": {},
                 "val": metrics(val[WAIT_TARGET][mva], base_va[mva]), "test": metrics(test[WAIT_TARGET][mte], base_te[mte]), "fit_s": 0})
    mean_va = np.full(len(val), y_tr.mean()); mean_te = np.full(len(test), y_tr.mean())
    rows.append({"algorithm": "Predict train mean", "params": {}, "val": metrics(val[WAIT_TARGET], mean_va),
                 "test": metrics(test[WAIT_TARGET], mean_te), "fit_s": 0})
    for name, params, make in candidates(args.seed):
        t = time.time()
        pipe = make().fit(Xtr, y_tr)
        row = {"algorithm": name, "params": params, "val": metrics(val[WAIT_TARGET], pipe.predict(Xva)),
               "test": metrics(test[WAIT_TARGET], pipe.predict(Xte)), "fit_s": round(time.time() - t, 1)}
        rows.append(row)
        print(f"  {name:18s} {json.dumps(params):70s} val MAE {row['val']['MAE']:.3f}  ({row['fit_s']}s)")
        if name not in best or row["val"]["MAE"] < best[name][0]["val"]["MAE"]:
            best[name] = (row, pipe)

    # selection uses VALIDATION MAE only; the test set is touched once for reporting
    win_name = min(best, key=lambda k: best[k][0]["val"]["MAE"])
    win_row, win_pipe = best[win_name]
    print(f"\nselected: {win_name} {win_row['params']}  val MAE {win_row['val']['MAE']:.3f}  test MAE {win_row['test']['MAE']:.3f}")

    # --------------------------------- prediction intervals (empirical, 80%)
    pv = np.clip(win_pipe.predict(Xva), 0, None)
    resid = val[WAIT_TARGET].to_numpy() - pv
    edges = np.quantile(pv, [0.25, 0.5, 0.75])
    bins = np.searchsorted(edges, pv, side="right")
    lo = [float(np.quantile(resid[bins == b], 0.10)) for b in range(4)]
    hi = [float(np.quantile(resid[bins == b], 0.90)) for b in range(4)]
    pt = np.clip(win_pipe.predict(Xte), 0, None)
    bt = np.minimum(np.searchsorted(edges, pt, side="right"), 3)
    low = np.clip(pt + np.array(lo)[bt], 0, None); up = pt + np.array(hi)[bt]
    coverage = float(np.mean((test[WAIT_TARGET] >= low) & (test[WAIT_TARGET] <= up)))
    width = float(np.mean(up - low))
    print(f"interval coverage on test: {coverage:.1%} (nominal 80%), mean width {width:.1f} min")

    # ---------------------------------------------------------- importance
    sample = test.sample(min(2000, len(test)), random_state=0)
    imp = permutation_importance(win_pipe, sample[WAIT_FEATURES], sample[WAIT_TARGET], scoring="neg_mean_absolute_error",
                                 n_repeats=5, random_state=0)
    importance = sorted(zip(WAIT_FEATURES, imp.importances_mean), key=lambda kv: -kv[1])

    # ----------------------------------------------------------- artifacts
    version = f"wait-{win_name.lower()}-{utc_stamp()}"
    bundle = {
        "model": win_pipe, "version": version, "algorithm": win_name, "params": win_row["params"],
        "features": WAIT_FEATURES, "trained_on": "synthetic", "trained_at": utc_stamp(),
        "interval_edges": edges.tolist(), "interval_lo": lo, "interval_hi": hi, "interval_nominal_coverage": 0.8,
        "metrics": {"val": win_row["val"], "test": win_row["test"], "test_interval_coverage": coverage,
                    "test_interval_mean_width": width, "fallback_test": rows[0]["test"]},
        "data": {"rows": len(df), "days": args.days, "seed": args.seed, "split_cutoffs": [str(c1), str(c2)]},
    }
    joblib.dump(bundle, MODEL_DIR / f"{version}.joblib")
    joblib.dump(bundle, MODEL_DIR / "wait_time_latest.joblib")
    append_registry({"model": "wait_time", "version": version, "algorithm": win_name, "trained_on": "synthetic",
                     "metrics": bundle["metrics"], "data": bundle["data"], "trained_at": bundle["trained_at"],
                     "note": "SIMULATED-data metrics. Not evidence of real-world accuracy."})

    # -------------------------------------------------------------- report
    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    names = [f"{r['algorithm']}" + (f"\n{list(r['params'].values())}" if r["params"] else "") for r in rows]
    ax[0].barh(names, [r["test"]["MAE"] for r in rows], color="#4f7cff"); ax[0].invert_yaxis()
    ax[0].set_xlabel("Test MAE (minutes, simulated data)"); ax[0].tick_params(axis="y", labelsize=6)
    ax[1].scatter(test[WAIT_TARGET], pt, s=4, alpha=0.3, color="#4f7cff")
    m = max(test[WAIT_TARGET].max(), pt.max()); ax[1].plot([0, m], [0, m], "k--", lw=1)
    ax[1].set_xlabel("Actual wait (min)"); ax[1].set_ylabel("Predicted (min)"); ax[1].set_title(f"{win_name} — test set")
    plt.tight_layout(); plt.savefig(REPORT_DIR / "wait_time_report.png", dpi=130); plt.close()

    (REPORT_DIR / "wait_time_report.json").write_text(json.dumps({"benchmark": rows, "selected": win_name, "version": version}, indent=2, default=str))
    md = [f"# Waiting-time model report\n", "> **All metrics are from SIMULATED data** (discrete-event simulator, `backend/app/ml/simulation.py`). "
          "They are an engineering baseline, not evidence of real-world accuracy. Re-validate on real `service_records` before relying on them.\n",
          f"* Version: `{version}`", f"* Rows (served tokens after cleaning): {len(df):,}; train {len(train):,} / val {len(val):,} / test {len(test):,} (chronological by date, cutoffs {c1}, {c2})",
          f"* Selection rule: lowest **validation MAE**; test set evaluated once.",
          f"* Target: `actual_wait_minutes = service_start − queue_entry` (PRD §4). Cancelled/no-show tokens are censored and excluded.\n",
          "| Model | Params | Val MAE | Val RMSE | Val R² | Test MAE | Test RMSE | Test R² |", "|---|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: r["val"]["MAE"]):
        md.append(f"| {r['algorithm']} | `{json.dumps(r['params'])}` | {r['val']['MAE']:.2f} | {r['val']['RMSE']:.2f} | {r['val']['R2']:.3f} | "
                  f"{r['test']['MAE']:.2f} | {r['test']['RMSE']:.2f} | {r['test']['R2']:.3f} |")
    win_on_mask = metrics(test[WAIT_TARGET][mte], pt[mte])
    gain = rows[0]["test"]["MAE"] - win_on_mask["MAE"]
    md += [f"\n**Selected: {win_name}** — test MAE {win_row['test']['MAE']:.2f} min on all rows. On the {mte.mean():.1%} of test rows where the non-ML fallback "
           f"is defined (an eligible counter is open) the model scores MAE {win_on_mask['MAE']:.2f} vs {rows[0]['test']['MAE']:.2f} for the fallback "
           f"({'improvement' if gain > 0 else 'NO improvement'} of {abs(gain):.2f} min).\n",
           f"**80% prediction interval:** empirical coverage on the test set = {coverage:.1%}, mean width {width:.1f} min "
           "(residual quantiles per predicted-wait bin, calibrated on the validation split).\n",
           "## Permutation importance (test sample, ΔMAE)", *[f"* `{k}`: {v:.3f}" for k, v in importance],
           "\n![report](wait_time_report.png)"]
    (REPORT_DIR / "wait_time_report.md").write_text("\n".join(md), encoding="utf-8")
    print("report -> ml/reports/wait_time_report.md")


if __name__ == "__main__":
    main()
