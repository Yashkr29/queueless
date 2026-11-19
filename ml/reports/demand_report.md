# Demand-forecast model report

> **SIMULATED data.** Not evidence of real-world accuracy.

Chronological split by date: train < 2025-05-12 <= val < 2025-06-02 <= test. First 28 days dropped (lag features need history). Prophet was not benchmarked (optional dependency).


## Horizon 30 min — selected **GradientBoosting**

| Model | Val MAE | Test MAE | Test RMSE | Test WAPE |
|---|---|---|---|---|
| GradientBoosting | 1.68 | 1.59 | 2.09 | 38.9% |
| XGBoost | 1.68 | 1.59 | 2.10 | 38.8% |
| RandomForest | 1.75 | 1.62 | 2.13 | 39.7% |
| Historical mean (4 weeks) | 1.83 | 1.72 | 2.28 | 42.0% |
| Seasonal naive (same window last week) | 2.31 | 2.18 | 2.94 | 53.4% |

## Horizon 60 min — selected **XGBoost**

| Model | Val MAE | Test MAE | Test RMSE | Test WAPE |
|---|---|---|---|---|
| XGBoost | 2.31 | 2.20 | 2.86 | 27.6% |
| GradientBoosting | 2.33 | 2.19 | 2.85 | 27.4% |
| RandomForest | 2.36 | 2.27 | 2.93 | 28.4% |
| Historical mean (4 weeks) | 2.50 | 2.43 | 3.20 | 30.4% |
| Seasonal naive (same window last week) | 3.18 | 3.07 | 4.01 | 38.4% |

## Horizon 120 min — selected **XGBoost**

| Model | Val MAE | Test MAE | Test RMSE | Test WAPE |
|---|---|---|---|---|
| XGBoost | 3.08 | 3.03 | 3.96 | 20.2% |
| GradientBoosting | 3.12 | 3.04 | 3.98 | 20.3% |
| RandomForest | 3.13 | 3.14 | 4.07 | 21.0% |
| Historical mean (4 weeks) | 3.38 | 3.41 | 4.55 | 22.8% |
| Seasonal naive (same window last week) | 4.42 | 4.12 | 5.50 | 27.6% |