# Tejas's handoff — features and forecasting

Human Tejas, GitHub `@tbhojo`. Own `halcyon/forecasting/`, matching
tests/notebooks and `docs/modeling.md`. Read rules/plan/contracts, claim your
issue and post a review. Start with contract-shaped fixtures while Andrew
publishes the shared package; do not wait idle.

First implement `Forecaster.predict(data, cutoff, target_weeks)` with origin-specific
historical-rate and last-known-price baselines. Return exact target_week/material keys,
finite bounded probability, positive price and `model_id`. Merge that baseline
first. Then add actual Spark lag/rolling/announcement features and a pooled
tabular classifier/regressor. Existing scikit-learn is sufficient initially;
coordinate added dependency pins with Andrew.

Gates:

- Each inner training origin has its own data cutoff. Outer-cutoff filtering
  alone does not prevent leakage. Future demand is known; future realized
  markets, supply, news and labels are not features.
- Same-week silver observations must become lagged/origin-safe features.
- Phase 1 private horizons are 14–26 from 208; Phase 2 private is 1–13 from 221.
- Develop on origins 130/156; reserve 182 for final holdout. Report Brier/MAPE
  by horizon/material and calibration where useful; no random splits.
- Test future-row mutation invariance, single-class/short-history cases and
  missing optional news. Recompute baselines per origin, never from week-208
  sample values. Explicitly log any fallback.

Publish feature/schema versions and model/config artifacts to the supplied run
directory. Andrew owns outer orchestration, gold/MLflow packaging and export;
AV owns policy. Give Andrew entry point/config, example output, meaningful
tests/backtest evidence and limitations with each handoff. Coordinate optional
news features with him without making core forecasts depend on an LLM endpoint.

Authenticate on your workstation as `tejasb3@illinois.edu`. Permissions were
verified; query a table for your own smoke check instead of repeating setup.
Review temporal/model-validation plans now, fix planning docs by PR, and notify
Andrew/AV when a shared contract is affected.
