# V2 improvement review — Tejas

Owner: Tejas (`@tbhojo`), issue #42. Scope: submission pipelines only; no video/UI.

## Decision

Keep historical disruption rates and carry-forward prices as the Phase 2 default.
Evaluate the already-exported price-only runner-up as a bounded **Phase 1** experiment,
not an automatic private-model upgrade. No new estimator, feature family, package,
or forecasting API is justified by current evidence. A better next submission is
an acceptance target, not a result we can promise.

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
| P0 keep | Retain historical Phase 2 forecast default | P | Short-horizon regression above; pooled classifier also fails dev evidence. Add explicit selection guidance rather than estimator code. | Tejas / small | No accidental use of26-week mean to justify13-week model promotion; final config/model identity and cutoff auditable. |
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
- Andrew reports a conditional-state disruption experiment on origins52–168
  with targets through182. This is new **unverified peer evidence**, not a
  promotion decision. Tejas requested the exact formula/script/artifacts and
  per-origin/horizon1–13 metrics before implementation. No new framework,
  classifier search, or claim of independent untouched validation is justified.
