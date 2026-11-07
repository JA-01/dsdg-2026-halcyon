# Forecasting

## Historical reference

`halcyon.forecasting.baseline:HistoricalForecaster` implements
`predict(data, cutoff, target_weeks)`. Each material receives its own disruption
frequency over released history through the cutoff and its last observed
benchmark price. No organizer sample values are used. Requests must have unique
integer target weeks strictly after a positive integer cutoff. Missing material
history is an error, not an invented forecast. A one-week or single-class history
is supported.

The model narrows `Dataset.as_of(cutoff)` itself even when the caller provides
an unfiltered dataset. `save_artifacts(directory)` writes rates, last prices,
training bounds and model identity after prediction.

Baseline smoke: actual CSV data through208, `InventoryPolicy`, independent
public/private windows, exported260 valid rows with SHA256
`734c30db0566c6968a43bc527958d264533fb22adf248f29f3d22bf825641247`.
Eight baseline regression cases passed, including future-label mutation,
one-observation history and invalid request boundaries.

For config-driven execution use:

```json
{"class": "halcyon.forecasting.baseline:HistoricalForecaster", "kwargs": {}}
```

Development origins are130 and156. Origin182 stays locked until final selection.
Future demand is public; future realized outcomes, markets, supply and news are
not features. Phase1 private horizons are14–26 from208; Phase2 private is1–13
from221. Financial simulator metrics are proxies, not official competition scores.
