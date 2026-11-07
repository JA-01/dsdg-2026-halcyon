# V2 improvement review: Jaseer (lead)

Incumbent: **54.10 public**, MLflow `7d2271940a5744c3bd3756a7071c72c4`, SHA-256 `2240be82…aead6`
(historical probabilities, carry-forward price, `OptimizedPolicy`). V2 has to beat it, and only the private
weeks 222-234 decide placement. This review covers the whole pipeline. It keeps only changes with evidence
behind them that stay close to the MVP.

## Evidence

[`jaseer-v2-evidence/estimate.py`](jaseer-v2-evidence/estimate.py) reproduces everything below in about 20
seconds from the repo root. Per-window raw cost, shock fill, diversification, naive cost and hindsight cost are
in [`windows.csv`](jaseer-v2-evidence/windows.csv). The script estimates the published formula. **It does not
match the organizer's scorer and has not been calibrated to any Kaggle score.** Use it to compare candidates,
not to predict scores.

- Naive is `NaivePolicy`. Hindsight is a per-material LP on realized capacity, lead and cost. Fill skill is 0
  when naive already fills all shock demand.
- Windows are h1-13. Set A starts at origins 52-169 and set B at 58-162, both in steps of 13. No target is past
  182. Windows overlap V1 development data, so this is not an untouched holdout.
- My estimator was written separately from Andrew's. It reproduces his numbers exactly: current policy 36.7 (A)
  and 31.5 (B), the same per-origin news Brier skill, and tilt k=3 at +2.89 per window with a worst of -7.2.

### Policy (F and R, 70% of score)

The table shows the change in estimated score per window against the current policy. "Shock" means the 8 of 19
windows where the current policy scores above 50, as 54.10 suggests the public window did. "Hedged" is the mean
of max(0, delta), the gain when the other final slot keeps current shares.

| Candidate | Mean | Worst | Wins | Shock | Calm | Hedged | Diversification |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Current | 0 | 0 | - | 0 | 0 | 0 | 0.98 |
| Tilt k=3 (Andrew #6) | +2.89 | -7.17 | 14/19 | -0.95 | +5.68 | +3.63 | 0.98 |
| **Tilt k=3 + `risk_buffer_weeks` 4** | **+3.07** | **-6.47** | **15/19** | **+0.69** | **+4.80** | +3.43 | 0.98 |
| Tilt k=5 | +3.88 | -12.93 | 13/19 | -2.00 | +8.16 | +5.17 | 0.96 |
| `diversification_penalty` 0.10 (config only) | +3.18 | -13.02 | 13/19 | -1.26 | +6.42 | +4.02 | 0.90 |
| `diversification_penalty` 0.05 (config only) | +4.26 | -26.84 | 11/19 | -4.16 | +10.38 | +6.43 | 0.79 |
| `base_buffer_weeks` 3 | -1.19 | -7.80 | 2/19 | +1.65 | -3.26 | +0.86 | 0.97 |
| `risk_buffer_weeks` 4 | +0.04 | -3.50 | 3/19 | +1.22 | -0.81 | +0.55 | 0.98 |

What this shows:

- Across the 19 windows, the current policy costs 14.0M more than hindsight. Our own holding is 5.3M and our
  shortage is 5.4M; most of the rest is purchase cost. Supplier choice is the largest lever that does not need
  new forecasts.
- A tilt saves money in calm windows but loses fill when the cheap supplier is the one that gets hit. A longer
  risk buffer does the opposite. Together they are the only candidate that is positive in both regimes.
- Lowering the diversification penalty, the config-only option, gains a similar mean but has a much worse tail.
  The MILP's L1 penalty switches between balanced and single source, so it either changes little or
  concentrates fully. Rejected.
- Tilting the MILP's lane weights inside the solve was dominated by the post-hoc tilt (k=4: +2.47 / -6.31).
  Rejected.

### Prediction (P, 30% of score)

The incumbent's probabilities equal the sample reference within 4.6e-5, and its prices equal it exactly, so P is
about 0. The rules clip P at 0. Since the policy does not read these columns, a CSV-only change cannot lower the
score, provided the published aggregation holds. Tejas's caveat: at cutoff 221, if the organizer's reference
stays at the week-208 rates, our historical probabilities are no longer exactly the reference, so the floor
argument is conditional there.

| Candidate | Mean P points | Notes |
| --- | ---: | --- |
| News `DisruptionModel(True)`, h1-13 only (#5) | +4.49 | Matches Andrew and Tejas per origin. Positive in 13/19 folds, floored at 0 in the rest. |
| Plus price 0.75 x last + 0.25 x trailing 52-week mean (#7) | +4.83 | +0.34 on top. Flat over the horizon, so orders are unchanged. Positive in 16/19. |

## Selection: use both final slots as a hedge

On Kaggle, the best private score among your selected submissions counts. This is standard Kaggle behavior;
humans should confirm it on the competition page. With two slots, the tilt's tail risk is covered by a slot that
keeps current shares:

- **Slot 1:** news P (#5) + tilt k=3 + `risk_buffer_weeks` 4.
- **Slot 2:** news P (#5) + current policy.

Both are Phase 2 runs at cutoff 221 that keep the public archive. The 54.10 file stays recorded as the
incumbent, not as a final slot, because its private rows were planned at cutoff 208.

## Final V2 list

| # | Item | Owner | Status |
| --- | --- | --- | --- |
| 1 | Equal eligible shares on exact-zero orders | AV | Merged (PR #47) |
| 2 | Phase 2 acceptance always verifies the archived public block | Andrew | Merged (PR #51) |
| 3 | Raw metrics by fold and by h1-13; historical private default | all | Agreed |
| 4 | Genuine cutoff-221 refresh: archived public rows plus fresh private rows | Andrew | Saturday noon |
| 5 | CSV-only news probabilities at h1-13; h>13 stays exactly historical; policy reads historical rates | Andrew | Fixed on main. Tejas and AV invariance checks pass |
| 6 | `OptimizationConfig.cost_tilt`: post-hoc tilt on positive optimizer rows, spilling above the q25 capacity, off by default | Jaseer's agent (lead reassignment; AV reviews) | PR for #56. The evidence script runs this exact code. Slot 1 only, not default. |
| 6b | `risk_buffer_weeks` 4 in the slot 1 config, `configs/phase1_v2_tilt_delta.json` | Jaseer's agent | Same PR. Needs `HistoricalRiskPolicy(config=...)` from PR #60 |
| 7 | Price blend 0.75 last + 0.25 trailing 52-week mean, flat at all horizons | Andrew (`halcyon/news/`) | PR #60. Orders unchanged |
| 8 | Production score estimator in `halcyon/` | - | Rejected. The evidence script lives in this doc folder. |
| 9 | After Phase 2, score the incumbent on 209-221 with this estimator and compare with 54.10 | Andrew | Calibration check before final selection |

Tonight's uploads (Phase 1, cutoff 208, at most 5 per day): U1 is `configs/phase1_v2_news_delta.json` (news P
only, held run `32244c21…`, SHA `59dc988b…5f07e3`). U2 is `configs/phase1_v2_tilt_delta.json` (U1 plus blend,
tilt k=3 and `risk_buffer_weeks` 4). Post each score with the CSV hash. If U2 beats U1 on public, that shows
the tilt helps in a shock-type window. Either way, both shapes stay as the two Phase 2 slots.

## Considered and dropped

| Idea | Why dropped |
| --- | --- |
| New disruption/price models, sweeps, news LLM | Existing news model already gives the P gain; no time to validate more |
| Pooled price runner-up for a final slot | Skill -0.12 on both sets; regresses h1-13 MAPE (Tejas) |
| Feeding news probabilities into the policy | No gain (Andrew); it would also remove P's floor protection |
| Larger tilts, lower diversification penalty | Higher mean but tails of -13 to -27 |
| Longer base buffer, lead or capacity quantile changes | Flat or negative mean |
| Tariff-announcement-aware costs | Only 30 announced rows in the data, so the lever is small |
| Hindsight orders on public rows after Phase 2 | Would make the public score meaningless and does not affect private; keep the archive |
| Rounding order quantities | No organizer evidence; fractional quantities are allowed |
| Video, UI, infrastructure | Out of scope |
