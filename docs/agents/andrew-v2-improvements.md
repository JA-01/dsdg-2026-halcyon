# V2 improvement review: Andrew

Owner: Andrew (`@andrewkwon0804-web`), issue #44. Incumbent: **54.10 public**, MLflow
`7d2271940a5744c3bd3756a7071c72c4`, SHA-256 `2240be82…aead6`, which I rebuilt locally byte for byte.

## Bottom line

The peer list (Tejas's board comment 6702129490) is sound, and I ACK all four items. It will probably not
beat 54.10, though. It keeps the same forecasts and the same active orders, and the zero-order share fix moves
diversification by about 0.006. The goal is to beat 54.10, so I propose two additions below. Both need a
decision.

## Evidence

Everything below uses a throwaway estimator of the published formula. **It is not organizer parity and has not
been compared with any Kaggle score**, because public truth arrives Saturday noon. My assumptions:

- Naive is `NaivePolicy`, which matches the sample's orders and shares.
- Hindsight is a per-material LP on realized capacity, lead and cost.
- Fill skill is `(shock_fill - naive) / (1 - naive)`, and 0 on a tie.

Use it to compare candidates, not to predict scores. Windows are h1-13, Phase 2 shaped. Set A is origins 52-169
step 13. Set B is the offset confirmation set, origins 58-162 step 13. No target is past week 182. These windows
overlap the V1 development data, so they are not an untouched holdout.

### Scores split by whether the window has shocks

| Window type | Estimated score, current policy |
| --- | ---: |
| Shocks, naive fill below 1 | 54-68 |
| Calm, naive fill 1 | 9-21 |

So 54.10 probably means the public window had shocks. **A calm private window could score far lower with no
change in the quality of our work.** Public score is a weak guide to private.

### P is exactly 0 and clips at 0

The incumbent's forecasts equal the reference, so P = 0. The rules clip each part to 0-1, so if the policy does
not read these forecasts, a worse forecast cannot lower the score. That changes the selection logic: "regresses
in some folds" does not block a forecast, as it would if losses counted.

Brier skill on set A, for the existing `halcyon.news.forecaster.DisruptionModel(use_news=True)`, not retuned.
Formula: `P(disrupted at origin + h) = material rate x lift(state at origin, horizon bucket)`, using pooled lifts
shrunk toward 1.

| Origin | 52 | 65 | 78 | 91 | 104 | 117 | 130 | 143 | 156 | 169 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Brier skill | 0.858 | 0.020 | 0.080 | -0.000 | -0.002 | 0.920 | -0.984 | 0.482 | 0.400 | -0.309 |

Mean 0.146, mean after flooring at 0 is 0.276, which is about **+5 points** (30 x 0.6 x 0.276), assuming price
skill near 0. It is positive in 6 of 10 folds and driven by a few large ones.

Set B confirms it: skill by origin 58-162 is 0.047, -0.081, 0.495, 0.028, 0.521, 0.575, 0.218, 0.095, -0.035.
Mean 0.207, floored mean 0.220, about +4 points, positive in 7 of 9. Tejas and AV signed off before seeing this,
so no peer has checked it independently.

Other forecast checks:

- **Price, 75% last + 25% trailing 52-week mean:** mean skill +0.025 (A) and +0.069 (B), positive in 8/10 and
  8/9 folds. About +0.3 to +0.8 points.
- **Price, pooled model (runner-up):** mean skill -0.12 on both sets, positive in 3/19 folds. This supports
  Tejas's finding. **It should not hold the second final slot on forecast grounds.**
- **Futures ratio:** no skill.

### Cost-tilted supplier shares are the largest F lever, and carry real risk

Current shares are nearly even (diversification 0.97) while supplier costs differ by up to 30% within a
material. HHI is quadratic, so a mild tilt gives up little R. I tested `shares ∝ exp(-k x relative trailing
cost)`, keeping weekly quantities and spilling above q25 capacity to other suppliers.

| k | Set A mean | Set A worst | Set B mean | Set B worst | Diversification |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0 (current) | 36.7 | 12.8 | 31.5 | 8.7 | 0.97 |
| 3 | 40.0 | 20.0 | 33.8 | 8.6 | 0.96 |
| 5 | 41.1 | 23.3 | 34.2 | 8.2 | 0.92 |
| 7 | 41.8 | 25.8 | 34.4 | 7.7 | 0.87 |
| 10 | 42.1 | 28.6 | 34.3 | 6.9 | 0.80 |

Change per window for k = 3, against k = 0:

- Calm windows: +5 to +9.
- Largest losses: -6.0 (170-182) and -7.2 (98-110). At k = 10 these become -19.8 and -26.1.

Means favor a tilt, but the loss falls on the shock windows that earn the most. k = 3 captures most of the gain
with the smallest downside. A public upload may understate the benefit if that window had shocks.

Other policy checks: changing the buffer (`base_buffer_weeks` 1 or 3) did not beat the current setting at k = 0,
and feeding news probabilities into the policy did not help. **So the policy should keep reading historical
rates**, which also keeps the P floor safe.

## Proposed list

| # | Item | Moves | Owner | Status |
| --- | --- | --- | --- | --- |
| 1-4 | Tejas's list: zero-order shares (done), archive verification and Phase 2 refresh, Pareto reporting, score receipts | validity | as listed | ACK |
| 5 | CSV `disruption_prob` from `DisruptionModel(True)`; policy still reads historical rates | P | Andrew (`halcyon/news/`) | Building as a candidate; not peer-checked |
| 6 | Tilt shares, k = 3 | F, some R | AV's path; AV has signed off | **Needs AV or Jaseer handoff** |
| 7 | Price blend, 25% trailing 52-week mean | P, small | Tejas's path | Optional; drop if it needs more than a few lines |
| 8 | Promote the score estimator to `halcyon/` and report it beside raw metrics | selection | Andrew | Only if 5 or 6 goes ahead |

Uploads are the only real test. Item 5 changes only the P columns, so its effect is isolated. Item 6 should be a
separate upload. Humans have 5 attempts a day.

## Dropped

New models or classifiers, parameter searches, higher buffers, an optimizer rewrite, LLM news, UI, video, and
fitting the estimator to one score.

## Repository cleanup, separate from score

`catboost_info/` and `.DS_Store` are tracked. `docs/candidates.md` still says neither candidate has a Kaggle
score.
