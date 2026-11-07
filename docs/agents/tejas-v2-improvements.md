# V2 improvement review — Tejas

Owner: Tejas (`@tbhojo`), issue #42. Scope: submission pipelines only; no video/UI.

## Decision

Keep historical rates/carry-forward prices as the policy inputs and fallback.
After independently checking Andrew's new evidence, accept an experimental CSV
candidate using the **existing** news-state disruption estimator for horizons1–13
only, without changing prices, orders or shares. This supersedes the initial
blanket deferral of disruption candidates, not the rejection of pooled classifiers.
Do not automatically promote the price-only runner-up for Phase2. No new model,
feature stack, dependency or API is needed. Beating54.10 remains unproven.

The human-reported incumbent is **54.10 public**, MLflow
`7d2271940a5744c3bd3756a7071c72c4`, CSV SHA-256
`2240be824b0808a9e70c78573259894f48a17e356134babe0a5daac9617aead6`.
Preserve it as fallback. It says nothing about unrevealed private performance.
The board identifies existing price+optimized runner-up
`5ef4cf179fd847329e5ac04b2f980149`; its Kaggle score is not established here.

## Evidence that changes the decision

`models.py:85–101` restricts training features to inner origins and training
labels to the outer cutoff. `models.py:137–146` supports historical risk with
learned relative prices. `features.py` and `spark.py` already provide matching
lagged/rolling, futures, announced-tariff, shipping, macro, capacity and demand
features. Rebuilding these is duplicate scope.

Recomputed from `outputs/forecast-dev/predictions.csv`, development origins
130/156 only, equally weighted rows. Both models use identical historical risk.

| Forecast horizon | Historical MAPE | Price-only MAPE | Relative error change |
| --- | ---: | ---: | ---: |
| 1–13, Phase 2-like | 0.064654 | 0.066085 | +2.21% |
| 14–26, Phase 1 private-like | 0.082277 | 0.078576 | -4.50% |
| 1–26 combined | 0.073466 | 0.072331 | -1.54% |

The combined mean hides a short-horizon regression. At origin156, short-horizon
MAPE rises from0.056286 to0.061066; at origin130 it improves from0.073022 to0.071105.
The full pooled classifier regresses Brier in three of four origin/window blocks
(`docs/modeling.md:45–54`), including0.188864→0.529426 at origin130/horizons1–13.
Neither result supports blanket promotion or new hyperparameter searches.

Price is only40% of the30% prediction component. A small average price gain is
not a large total-score gain; clipping, evaluator aggregation, and changed
orders prevent translating these local errors into a promised Kaggle increment.
Historical forecasts target the competition's prediction reference, so meaningful
remaining gains must be demonstrated, not inferred from model complexity.

Origin182 has already been evaluated once according to the board. Do not reuse
it to choose V2 settings, and do not label it untouched. Development130/156 can
support bounded comparisons but has already informed V1 choices. Released public
209–221 is retrospective diagnosis after Phase 2, not new validation.

## Ranked full-pipeline improvement list

Score columns name the component potentially affected, not an estimated gain.
Effort is qualitative; cross-owner proposals require that owner's agreement.

| Priority / disposition | Improvement | Component | Evidence / smallest action | Owner / effort | Acceptance |
| --- | --- | --- | --- | --- | --- |
| P0 keep | Preserve incumbent and record score receipts | P/F/R | Existing run/hash above; score is human-reported. Record each new CSV hash, release, cutoff, config, Kaggle receipt and remaining daily attempts. No submission automation framework. | Andrew + human / small | A claimed improvement has an actual score greater than54.10 on comparable public data; private result remains unknown. |
| P0 keep | Select by forecast and policy tradeoffs, not cost-only tie breaking | P/F/R | Board's V1 rule chose historical+optimized by near-tied cost/simplicity despite slightly better price MAPE in runner-up. Publish a predeclared Pareto table from existing comparison artifacts: Brier, MAPE, proxy cost, shock fill, diversification per fold/window. No fabricated weighted official total. | Andrew, AV, Tejas / small | Regressions and horizon1–13 are visible before selection; explicit retained/rejected candidates and reasons. |
| P0 keep | Execute genuine Phase 2 refresh using existing machinery | P/F/R | `halcyon.phase2`, `docs/phase2-runbook.md`, contracts already describe pinned221 release, archived public rows, fresh private inventory. This is an operational gate, not a new architecture. | Andrew / existing path | Real released data through221; source versions pinned; private targets222–234 from221; exact archived public block;260 validated rows and remote artifacts. |
| P0 keep | Historical policy inputs and fallback; bounded CSV-only state candidate | P | Short-horizon price regression and pooled-classifier regressions still block those promotions. Existing news-state estimator now has independent additional-origin evidence below. | Tejas review; Andrew integration / small | Policy inputs/decisions/prices unchanged; candidate only changes h1–13 CSV probabilities; preserve baseline and validate bytes. |
| P1 bounded experiment | Score existing price-only Phase 1 runner-up if daily attempt available | P, possibly F | Already exported and accepted per board; tests a real artifact without implementing a model. Keep policy/config comparison clear; AV notes price forecasts can change policy costs. | Andrew + human / small | Validate exact bytes/lineage, record score; do not use public success alone to promote private short-horizon model. |
| P1 investigate before change | Identify an actual policy/simulator mismatch or robust dev tradeoff | F/R | Kaggle rules specify capacity cancellation, lead time,2% holding,5×shortage,70%salvage, fresh stock. AV already implements finite-horizon optimization and sensitivities. Ask for organizer semantics where ambiguous; do not replace working optimizer speculatively. | AV / bounded | Concrete discrepancy or repeatable130/156 raw-metric gain, independent windows, explicit assumption sensitivity, valid export. |
| Conditional only | Fix demonstrated release/evidence/export defects | P/F/R validity | Existing validator, run manifest, Delta writes and acceptance runner should be exercised first. No broad rewrite. | Andrew / defect-dependent | Reproduce the specific failure, fix it, real job/readback acceptance; preserve valid incumbent bytes where behavior is unchanged. |
| Drop for this iteration | New classifier, CatBoost/neural models, calibration/ensemble search | P | Current pooled classifier fails existing evidence; only two repeatedly used dev origins, no independent untouched holdout. | Tejas / avoid | Reopen only for a concrete diagnosis and agreed independent evidence, not desired score. |
| Drop for this iteration | New LLM/news extraction stack or richer features by default | P/F/R | Existing optional news pipeline belongs to Andrew; no incremental score evidence established by this review. Existing numeric features already cover main structured sources. | Andrew + Tejas / avoid | Only an already-supported, bounded ablation with origin-safe events and clear gain can justify promotion. |
| Drop | UI, video, dashboards, model registry, serving, distributed training, generic optimization infrastructure | None required for CSV path | Human explicitly excludes video; competition data and batch size do not justify added systems. | All / none | No new dependency or code surface. |

## Verification and handoff

Review covers the competition rules/cheat sheet, contracts/plans/handoffs, forecasting
source/tests/notebooks and saved dev artifacts, with independent read-only reviews
of integration/news/Phase2 and policy/simulator. The actual dev runner completed
in40.28s and reproduced every published origin/window error above.
No source-model/policy/API change is proposed, so no new permanent tests.

Current owned entrypoint for repeating the development check:

```sh
.venv/bin/python notebooks/forecasting/evaluate.py --output /tmp/halcyon-v2-tejas-dev
```

This executes only130/156, saves predictions/metrics/calibration/model artifacts,
and does not evaluate182. Peers agree the final shared list on the board; Andrew
owns remote CSV regeneration and AV owns policy changes. Tejas signs off only the
owned review and explicitly accepted forecasting changes, not unseen jobs/scores.

## Peer alignment

- AV accepts retaining historical Phase2 defaults and limiting the price-only
  runner-up to a Phase1 experiment (board comment6702105343).
- Tejas accepts AV's bounded uniform eligible shares on exactly-zero optimizer
  orders: no procurement change, possible diversification improvement, official
  score effect unknown. Positive orders stay unchanged.
- Andrew acknowledged the original four-item list (board6702166956). Tejas
  independently checked his existing news-state proposal and accepts the
  probability-only experiment under the invariants below (board6702206798).
  No new classifier search or claim of untouched validation is justified.

### Bounded integration findings

`halcyon/accept.py:47–49,79–81` compares archived public rows only when
`--retained-from` is explicitly supplied; manifest provenance is not sufficient
to trigger the check. Tejas accepts making Phase2 archive verification mandatory,
with Andrew owning the fix. This is a real acceptance gap, not a model feature.
`halcyon/phase2.py:56–58` also names default configs by release only, so generating
selected and runner-up for one release overwrites the earlier local config.
Use distinct explicit `--output` names immediately; Andrew can choose a bounded
safe-default fix. No handoff to Tejas is requested for either shared file.

Independent forecast/scoring review passed: horizon calculations, cutoff-safe
training, historical-risk mode, feature coverage, and score-claim boundaries agree
with source and saved metrics. Initial exploratory scout jobs were unavailable
(503); no findings are attributed to them. The subsequent focused reviews use
the actual known source files.

Existing news evidence is also a reason not to add a new extraction/model stack:
`docs/news-events.md:25–35` reports near-term improvement over its no-news
ablation but a severe origin130 regression against historical rates. Its state
lift is already implemented (`halcyon/news/forecaster.py`); do not duplicate it.

Independent integration/policy review also passed. The archive gap is specifically
the remote acceptance command: the production runner already requires Phase2
archive configuration and verifies archived source bytes. Simulator diversification
includes zero-order rows; official weighting remains unspecified.

## New evidence after initial sign-off — issue #52

Andrew published `docs/agents/andrew-v2-improvements.md` after the initial review.
Independent runtime probe used `DisruptionModel(True/False)` unchanged, compared
with `HistoricalForecaster`, on origins58–162 step13 and horizons1–13. Every model
receives `data.as_of(origin)`; labels are joined only for evaluation. Last target
is175, not the182-origin holdout. These windows overlap prior development data;
this is an additional robustness check, **not independent unseen validation**.

| Origin | Historical Brier | News-state Brier | News-state Brier skill |
| --- | ---: | ---: | ---: |
| 58 | 0.094222 | 0.089764 | 0.047313 |
| 71 | 0.027430 | 0.029642 | -0.080638 |
| 84 | 0.004337 | 0.002192 | 0.494576 |
| 97 | 0.625378 | 0.607963 | 0.027846 |
| 110 | 0.526809 | 0.252433 | 0.520826 |
| 123 | 0.362851 | 0.154228 | 0.574955 |
| 136 | 0.080444 | 0.062907 | 0.218001 |
| 149 | 0.144346 | 0.130648 | 0.094895 |
| 162 | 0.164957 | 0.170748 | -0.035107 |

Mean per-origin raw skill is0.206963;7/9 origins improve. No-news mean skill
is0.182073. Price forecasts exactly match historical carry-forward throughout.
This supports a bounded existing-estimator experiment, not a promised gain.

### Clipping argument: conditional, not empirical score proof

If incumbent prices/probabilities exactly equal the evaluator's references,
its prediction component is0. If prices remain identical and policy outputs
are frozen, the published formula gives
`30 * clip(0.6 * Brier_skill, 0, 1)` prediction points; negative skill then cannot
reduce that component below the incumbent's0. On the nine historical windows,
the mean of that hypothetical expression is3.956824 points. This is **not an
official score estimate, expected Kaggle gain, or new acceptance threshold**.
Unknown reference definitions/aggregation and the unchanged-policy requirement
must not be hidden. Do not floor individual material/horizon errors before
computing the window's aggregate skill, and do not apply this argument to price
changes or a candidate whose incumbent prediction component is already positive.

### Real export smoke and precise accepted boundary

Executed current `plan_windows` at208 using `HistoricalForecaster` and
`OptimizedPolicy`, with independent public/private calls. Replaced only the130
public probabilities using the existing news-state estimator, then called
`build_submission` and `write_submission` on the actual data. All260 rows passed;
all other CSV columns were exactly identical, as were all130 private rows.
Temporary CSV SHA-256:
`59dc988ba37dce62c47a6eb4f18169e8d9ef69fdc14cbc2e191349c87a5f07e3`.
Temporary directory was removed; this is smoke evidence, **not a remote release
artifact or uploadable deliverable**. Production wiring was not changed here.

Accepted implementation belongs to Andrew's existing integration/news scope:
policy must still receive historical forecasts; submission-only probabilities
use the existing estimator for h1–13. Leave h14–26 historical explicitly:
the estimator's long-horizon fallback is a **smoothed** rate and is not identical
to `HistoricalForecaster`. Phase2 uses h1–13 private from genuine221 data while
retaining the archived public block. Check exact order/share/price invariance
against a same-code/same-release baseline and preserve both model identities,
cutoffs and configuration in lineage before remote release.

Do not combine this experiment with cost-tilted shares or the optional price
blend: their effects would confound it and invalidate its fixed-policy argument.
Cost tilts remain AV-owned and require the stated handoff; Tejas grants none.
Defer the price blend: no new forecast code is necessary to test this candidate.
Do not promote a hindsight/naive-normalizer estimator into production merely to
rank this experiment; existing raw metrics and the isolated formula suffice,
and official simulator parity has not been established.
