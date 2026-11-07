# Final candidates

Phase 1 candidates, built from pinned Delta release `weeks-1-208-18caf03f890c`, all tables at version 1.
Selected scored **54.10** on the public leaderboard (human-reported). Runner-up has no recorded score. All costs
are local proxy estimates, not organizer parity. Phase 2 reruns replace both (see [the runbook](phase2-runbook.md));
add those runs here when they exist.

| Slot | Forecast | Policy | MLflow run | CSV SHA-256 |
| --- | --- | --- | --- | --- |
| Selected | `HistoricalForecaster` | `OptimizedPolicy` | `7d2271940a5744c3bd3756a7071c72c4` | `2240be824b0808a9e70c78573259894f48a17e356134babe0a5daac9617aead6` |
| Runner-up | `PooledForecaster(disruption_mode="historical")` | `OptimizedPolicy` | `5ef4cf179fd847329e5ac04b2f980149` | `dbf562db77584b2ea0d6e27fb8ce4f3d395b5bdeb782871d3cd3957dbebe15b0` |
| V2 candidate, no score yet | `DisruptionModel(use_news=True)` | `HistoricalRiskPolicy` | `32244c21c3ed44da8eafda2ed2f4acae` | `59dc988ba37dce62c47a6eb4f18169e8d9ef69fdc14cbc2e191349c87a5f07e3` |
| Earlier fallback | provisional rate/carry-forward | `InventoryPolicy` | `a289e8d2b57240fe8dfd7955f9bfb89b` | `734c30db0566c6968a43bc527958d264533fb22adf248f29f3d22bf825641247` |

Files are under `/Volumes/workspace/halcyon/artifacts/runs/<run>/` and in MLflow experiment
`/Shared/halcyon/runs`. Selected was built from `5a74c63`, which includes the week-key fix. Runner-up was
built from `58392a3`, before it; the fix only rejects malformed input, and the selected file's bytes did not
change across it. To re-verify a run: `python -m halcyon.accept <run>`.

## How these were chosen

The rule was posted on the board before the comparison ran: lowest summed proxy cost across the four
development windows, with candidates within 1% tied; ties go to higher mean shock fill, then simpler
components. Holdout origin 182 was then evaluated once, for selected and baseline only, and could not change
the pick.

Development origins 130 and 156, MLflow `16866c7e72844d24a16510f18d140f2d`:

| Candidate | Summed proxy cost | Mean MAPE | Mean fill | Mean shock fill | Mean diversification |
| --- | ---: | ---: | ---: | ---: | ---: |
| historical + optimized (selected) | 19,122,665 | 0.0735 | 0.9904 | 0.9884 | 0.974 |
| price + optimized (runner-up) | 19,126,450 | 0.0723 | 0.9904 | 0.9884 | 0.974 |
| price + inventory | 19,726,540 | 0.0723 | 0.9824 | 0.9780 | 0.937 |
| historical + inventory | 19,728,250 | 0.0735 | 0.9824 | 0.9780 | 0.937 |
| baseline (historical + naive) | 24,196,760 | 0.0735 | 0.9454 | 0.9125 | 0.000 |

Selected won the tie on simpler components. The cost rule does not reward price accuracy, which counts toward
the Prediction score, so the runner-up takes the second final slot.

Holdout, MLflow `e4f7709b072745acb21e8e882cb87dfe`:

| Window | Selected cost | Baseline cost | Change | Selected fill | Baseline fill |
| --- | ---: | ---: | ---: | ---: | ---: |
| 183-195 | 4,505,357 | 4,573,592 | -1.49% | 0.9994 | 1.0000 |
| 196-208 | 4,736,407 | 4,761,654 | -0.53% | 0.9963 | 1.0000 |

These were calm windows, so the holdout says little about behavior under shocks.

## Known limitations

- **Prediction score:** disruption forecasts are flat historical rates, so Brier skill is 0 by construction, and
  selected has zero price skill too. The tested models did not beat these rates on disruption.
- **Simulator:** we do not have the organizer's starter code. Initial stock, cost reference, timing, rounding and
  hindsight rules are assumptions listed in [simulator-assumptions.md](simulator-assumptions.md).
- **Fractional orders:** 52% of selected's `order_units` are not whole numbers. The rules allow it, but how the
  organizer's simulator treats them is unknown.
- **Unwarned shocks:** policy reversals give no warning by design, so forecasts cannot anticipate them.
- **News:** it improved near-term Brier over the same model without news, but is not in either candidate. See
  [news-events.md](news-events.md).
