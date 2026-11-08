# Final-pair handoff (phase-2 run, v2)

**Status: PHASE-2 RUN COMPLETE. Final pair v2 selected. Orchestrator Jaseer's Claude (@JA-01) signs off after the integration merge.** Updated 2026-11-08 UTC. Humans alone upload to Kaggle and choose the final selections.

## 0. Phase-2 run (#148–160): what changed and why

**Final pair v2** (the v1 pair is preserved as git tag `final-pair-v1`; the v1 record follows in §§1–6):

| Selection | Code (`halcyon/submit.py`) | CLI | SHA256 (data through 221) |
|---|---|---|---|
| **Primary** | `MODELS = (strategy_expected.predict_tariff, price.predict, policy.plan)` | `python -m halcyon.submit --out p.csv` | `b9ae48a91aa618f1fa2ee18140f3087d2ca7d232a36c30e3827e05024902f084` |
| **Second** | `HEDGE_MODELS = (partial(events.predict_shock, base=strategy_expected.predict_tariff), price.predict, policy_scenarios.plan_kes_overlay)` | `python -m halcyon.submit --hedge --out h.csv` | `86eb8095848504bfa064845051c3e6c2d8cd3ab47c37b2a67abd8ec65c2731b1` |

- **The only change from v1** is the disruption probability on 22 private rows: KES aluminum + semiconductors, weeks 224–234, now held at ≥0.917. Kestria's published tariff hike (0.10 → 0.35 at 224) makes those rows "disrupted" under the label rule (tariff > base), and every announced hike in history took effect (5 supplier rows, 3 of 3 campaigns). Orders, shares, prices and all public rows are **byte-identical** to the corresponding v1 build: the primary to `0da997d7…` and the hedge to `cf481a44…`, as checked in Tejas's EVAL 2. So the primary's public block is the champion's: local 71.363070, official receipt 70.76 from the original upload (`984a0b19…`; that original file was not byte-compared). The hedge's public block keeps its own, different orders: local 64.315137.
- **Evidence (local estimates):**
  - Private scenario matrix (`halcyon/scenarios_p2.py`, 19 scenarios weighted by the #152 signal calibration): best-of-two **75.012293 vs 74.406458** for v1, no scenario where it loses, worst 24.55 vs 24.13.
  - 11 historical origins: primary 51.733987 (+0.059 vs champion, gain only at 117, 0 losses); hedge 49.374284.
  - Weeks 209–221 (cutoff 208): unchanged, 71.363070 / 64.315137 local, by byte identity.
- **Risk:** if Kestria reverses or delays the tariff, those 22 probabilities are wrong. The 5% reversal weight is a judgment; all 3 historical campaigns were honored. The matrix covers a reversal only in an otherwise calm path.

**Phase-2 findings (#152, from data through 221):**
- No supplier is hit at 221.
- Open signals, with #152's scenario-design **judgments** (small historical samples, not calibrated probabilities): VAL cobalt export ban about 80% (basis 11.6%; clean basis flags were followed by a hit 6/6 times, median lag 3 weeks). Kestria restriction on rare earths only about 70% (any rare-earth restriction, including the wide case, about 80%). Kestria tariffs at 224 about 95%. Merrow lane disruption (0.75× capacity, +3 weeks lead on KES+SUN) about 35%. Kestria-wide restriction (historical comparator 0.20×, +3 lead) about 10%.
- Phase 2 itself showed a warning ladder that came true with a longer lag (KES lithium: 3 weeks after the accident headline, against 1–2 historically) and a fizzled false alarm (Valdmar lithium curbs, cancelled at 211).

**Rejected this run (local estimates; full tables on each issue):**

| Candidate | Scenario-matrix pair (partner) | Weeks 209–221 | 11 origins | Why rejected |
|---|---:|---:|---:|---|
| #149 expected plan, full (`strategy_expected.MODELS`) | 76.785 (hedge_v1) | 60.354 | 51.176 | Best on the synthetic matrix, but −11 on the only real phase-2 window. 80% of that comes from capping unsignaled warnings, which phase 2 punished. The matrix rewards that cap by construction. |
| #149 probabilities only (E_P) | 76.375 (hedge_v1) | 62.725 | 51.746 | Same probability cap; the (E_P, hedge) pair scores 64.32 vs 71.36 on 209–221 |
| #149 orders only (E_orders) | 74.803 (hedge_v1) | 68.992 | 51.105 | Leaner buffer: −0.57 historically and −2.37 on 209–221 |
| #150 Kestria escalation (`strategy_kes`) | 74.167 (champion); 67.080 (hedge_v1) | 64.315 | 49.315 | As the champion's partner it is below the v1 hedge's 74.406 |
| #151 broad shock insurance (`strategy_shock`) | 74.124 (champion); 71.716 (hedge_v1) | not scored | 49.485 | As the champion's partner it is below 74.406. AV's human forbade scoring 209–221. |

**Process:** evaluations ran on Tejas's machine and then Andrew's, by human directive; the orchestrator workstation ran no simulations after that directive. Every candidate module stays on `main` for reference: `strategy_expected`, `strategy_kes`, `strategy_shock`, `scenarios_p2`. **Verification (Andrew's machine, PR #160 head `4750b0d`):**
- Full `pytest -q`: **112 passed**.
- CLI builds: primary `b9ae48a9…` and hedge `86eb8095…`, both 260 rows, both matching EVAL 2.
- Public rows (weeks 209–221) equal the champion (`0da997d7…`) and hedge_v1 (`cf481a44…`) rebuilds.
- Exactly 22 private rows differ per file, all of them `disruption_prob` (aluminum + semiconductors, weeks 224–234, ≥0.9167).

**Upload files:** canonical CSVs are in Tejas's EVAL 2 gist https://gist.github.com/tbhojo/1ea7a992d133ace1a5ced6079223872a and are copied locally to `artifacts/final-v2/`. The hedge's MILP can return a different near-optimal plan on other machines, so upload the canonical bytes rather than a fresh rebuild.

---

# v1 record: pre-refit run

This run was human-authorized by Jaseer. It covered three tracks: policy (#141), FX defects (#142), and independent research (#143). All numbers are **local estimates over the 11 historical origins 65, 78, ..., 195** (13-week horizon, data cut at each origin). Nothing was trained, tuned, selected, or scored on weeks 209–221, and leaderboard feedback was not used. In v1, the primary was the unchanged champion and the second file was the combined hedge; both are superseded by §0.

## 1. Verdict

| Selection | Code | CLI build at data through 221 | SHA256 |
|---|---|---|---|
| **Primary (unchanged champion)** | `submit.MODELS = (disruption_news.predict, price.predict, policy.plan)` | `python -m halcyon.submit --out <primary.csv>` | `0da997d7c1ba771af1d59a7c678f76e79b7b9f039ced1fd4765ab09468c2481d` |
| **Second (new)** | `submit.HEDGE_MODELS = (partial(events.predict_shock, base=disruption_news.predict), price.predict, policy_scenarios.plan_kes_overlay)` | `python -m halcyon.submit --hedge --out <hedge.csv>` | `cf481a4489503e1d22b1bba3389d9d73f3df67574b5ba91795d9472de8577155` |

- The primary is byte-identical to the preserved incumbent rebuild behind the **official 70.76** champion. Its model code is unchanged.
- The second selection replaces the KES-only hedge (`events.plan_shock`, now removed). It combines the scenario policy with the same authorized KES assumptions: KES capacity ×0.37 from week 224 and a probability floor of 0.6. The scenario policy is the exact-fill version (#129/#137), with the #147 fixes for exact service and strict MILP status.
- **Historical best-of-two: 53.993500 mean / 34.452428 worst**, compared with **51.674722 / 34.452428** for the old pair. The old hedge was identical to the primary on every historical origin. The gain is **+2.318778**, with wins at 104 and 169 and no losses, because best-of-two cannot score below the primary.
- Both windows are honest: public rows use cutoff 208 and private rows use cutoff 221. The hedge's public orders differ from the primary's. Andrew suggested `ps.compose` instead, keeping the primary's public rows. Its private rows are identical, and final scoring uses only private rows, so the simpler single tuple was kept.
- The data already run through week 221 (`release_cutoff = 221`), so the hashes above are the refit-through-221 private candidates. A rerun on the same data must reproduce them.

## 2. Per-origin evidence (local estimates)

| Origin | Primary | Hedge | Best-of-two | Gain | FX (fixed) | Scope | FX+scope |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 65 | 34.452428 | 34.201380 | 34.452428 | 0 | 34.452428 | 34.452428 | 34.452428 |
| 78 | 48.003793 | 47.206345 | 48.003793 | 0 | 48.003793 | 48.030428 | 48.030428 |
| 91 | 62.663886 | 61.204592 | 62.663886 | 0 | 62.663886 | 62.663886 | 62.663886 |
| 104 | 66.108076 | 69.290266 | 69.290266 | +3.182190 | 68.035348 | 66.104883 | 68.032154 |
| 117 | 82.928605 | 82.857898 | 82.928605 | 0 | 84.506432 | 83.009810 | 84.587637 |
| 130 | 58.725472 | 57.813509 | 58.725472 | 0 | 58.725472 | 58.725472 | 58.725472 |
| 143 | 45.570801 | 33.294472 | 45.570801 | 0 | 45.570801 | 45.613546 | 45.613546 |
| 156 | 47.495071 | 37.190453 | 47.495071 | 0 | 47.495071 | 46.510142 | 46.510142 |
| 169 | 36.714931 | 59.039295 | 59.039295 | +22.324363 | 36.714931 | 36.714931 | 36.714931 |
| 182 | 50.096274 | 37.237602 | 50.096274 | 0 | 50.096274 | 50.098365 | 50.098365 |
| 195 | 35.662606 | 23.129399 | 35.662606 | 0 | 35.662606 | 42.381813 | 42.381813 |
| **mean** | **51.674722** | 49.315019 | **53.993500** | **+2.318778** | 51.993367 | 52.209609 | 52.528255 |
| **worst** | 34.452428 | 23.129399 | 34.452428 | 0 | 34.452428 | 34.452428 | 34.452428 |

Mean P/F/R: primary 0.259045/0.719879/0.503608; hedge 0.259045/0.626819/0.549030. Fill skill is 0.386950 for the primary and 0.425173 for the hedge. The hedge has the same forecasts as the primary historically and changes only orders. `predict_shock` is inactive before week 224, so the exact `HEDGE_MODELS` tuple scores the same as the plain scenario planner. Andrew (#141) and the orchestrator reproduced these numbers independently and exactly.

**Hedge downside, if it were the counted file:** mean −2.359703, 2 wins/9 losses, maximum loss 12.858672 at 182, and worst 23.129399 at 195. The second file is therefore a complement. It must never replace the primary.

### Sensitivity of the best-of-two gain

| Check (post-#147 hedge) | Best-of-two gain |
|---|---:|
| Standard scorer | +2.318778 |
| Combined-only-P clipping (`clip(.6·brier_skill + .4·price_skill)`) | +2.318778 (pair mean 53.648248 vs 51.329470) |
| Exclude origin 169 (outlier) | +0.318219 |
| Exclude both 104 and 169 | 0.000000 |
| Exclude 195 | +2.550655 |
| Simulator opening stock = next-5-week sum | +2.344701 |
| Simulator shortage cost 3 / 8 | +2.050758 / +2.485443 |

The whole gain comes from two shock windows. Excluding 169 leaves +0.32, all from origin 104. The direction holds under every scorer assumption checked. The hedge cannot lower best-of-two below the primary at any origin. Its only cost relative to the old KES hedge is plain S5 (−1.10, below).

### Private stress (synthetic, secondary evidence; scores on weeks 222–234; post-#147 hedge)

| Path | Primary | Old KES hedge | New hedge | Old pair best | New pair best | Unmet units: primary / old / new |
|---|---:|---:|---:|---:|---:|---|
| S0 calm | 37.37 | 35.46 | 24.42 | 37.37 | 37.37 | 0 / 0 / 0 |
| S1 tariff | 45.56 | 40.60 | 31.83 | 45.56 | 45.56 | 0 / 0 / 0 |
| S2 +VAL cobalt ban | 51.45 | 41.58 | 32.78 | 51.45 | 51.45 | 0 / 0 / 0 |
| S3 +KES rare-earths ban | 83.00 | 75.34 | 71.72 | 83.00 | 83.00 | 0 / 0 / 0 |
| S4 +MERROW closure | 58.97 | 64.35 | **83.75** | 64.35 | **83.75** | 122,643 / 90,264 / 596 |
| S5 KES-wide ban | 52.33 | **84.13** | 83.03 | **84.13** | 83.03 | 155,152 / 0 / 0 |
| early dual ban | 78.26 | 69.81 | 69.65 | 78.26 | 78.26 | 415 / 449 / 196 |
| late dual ban | 74.39 | 69.05 | 63.94 | 74.39 | 74.39 | 0 / 0 / 0 |
| short dual ban | 76.50 | 67.29 | 61.41 | 76.50 | 76.50 | 0 / 0 / 0 |
| persistent dual ban | 80.77 | 76.89 | 73.44 | 80.77 | 80.77 | 0 / 0 / 0 |
| dual ban plus closure | 58.97 | 64.35 | **83.75** | 64.35 | **83.75** | 122,643 / 90,264 / 596 |
| severe KES-wide ban | 46.95 | 65.68 | **74.75** | 65.68 | **74.75** | 358,158 / 188,714 / 98,974 |
| severe KES plus closure | 43.81 | 60.32 | **72.89** | 60.32 | **72.89** | 391,803 / 231,683 / 109,882 |

S0–S5 were reproduced by the orchestrator; the 7 timing/severity paths come from Andrew (#141). The new pair is at least as good as the old pair on every path except plain S5 (−1.10). Nine of the 13 paths are carried by the primary in both pairs. These paths have no probabilities attached, so they are not forecasts.

## 3. Track outcomes

| Track | Result | Decision |
|---|---|---|
| #141 policy (Andrew) | The MILP audit recomputed the true simulator cost of every plan on 130 real instances (11 origins × 10 materials + cutoff 221). #137 fills are exact. **Two new defects were fixed in PR #147** (`9f5da22`), each with a failing-before/passing-after test: (1) `served ≤ demand` let the optimizer withhold stock to dodge the safety-stock penalty (objective optimistic in 104/130 instances, up to 0.68%); (2) a time-limited status-1 MILP point was silently accepted, and now only status 0 is accepted (retry, then raise). After the fixes the objective equals simulator cost (max rel err 4.6e-12). Solves take median 1.2 s / max 8.7 s. Zero-capacity, tie and window-edge salvage paths were verified. | Second selection = combined hedge (PR #146). Andrew's per-origin CSV, stress CSV and scripts are on [#141](https://github.com/JA-01/DSDG-Hackathon/issues/141). |
| #142 FX (Jaseer's Claude worker; AV owner-review passed) | Both defects reproduced with failing tests and fixed in PR #145 (`1caacdc`). Body-only lane expansion now uses `disruption_news._scoped_reports`. "Tensions ease after talks with X" now cancels the warning. Thresholds and priors are unchanged. Historical: FX 51.993367 (+0.318645; wins 104/117; 0 losses; ex-195 +0.350510). FX+scope 52.528255 (+0.853533; 6W/1L; ex-195 +0.266965). The fixes change **0** probabilities at every historical origin, so they match the earlier provisional numbers. | **Not wired.** FX-wired primary and hedge files are **byte-identical** to the selected files at both cutoff 208 and cutoff 221, so FX would change no official row. The module is correct and kept as a challenger. |
| Scope (`disruption_scope`) | 52.209609 (+0.534887, 5W/2L); ex-195 **−0.083545**; loss −0.984929 at 156 | **Rejected:** the gain is concentrated at 195. |
| #143 research (Jaseer's Claude worker) | Learned price jump 50.889822 (−0.784901, 2W/8L); price expert aggregation 51.287039 (−0.387683, 1W/8L); prequential probability-residual shrinkage 51.147805 (−0.526918, 3W/5L) | **All rejected** by the predeclared gate. No code retained. Diagnosis: with decisions fixed, perfect probabilities would add 11.25 points on average and perfect prices 10.98. Probabilities lose to naive at 91/130/169, and prices lose at 91/117. |

Independent checks:
- **Cutoff safety (Tejas):** 48 exact tamper/removal comparisons passed at 65/117/195 for scenario, scenario+KES, scope, FX and FX+scope. All public blocks are cutoff-208-only ([#141 comment](https://github.com/JA-01/DSDG-Hackathon/issues/141#issuecomment-6718009368)).
- **Cross-machine parity:** before #147, Tejas reproduced the hedge byte-for-byte and AV matched within ≤3.3e-16. **After #147 the hedge is not bit-reproducible across machines.** AV (Python 3.14, same scipy 1.18.1) got SHA `927ae95c…`: 37/130 private rows differ, order units by up to 812 and shares by up to 0.20. These are alternative near-optimal MILP plans within `mip_rel_gap=1e-4`, not a defect. Their synthetic scores differ by ≤0.17 (S4 −0.03, S5 +0.02), matching the orchestrator's gap check. At refit, treat the hedge as one canonical build: record the hash of the exact uploaded bytes, and do not expect other machines to reproduce it. The primary remains byte-reproducible.
- **Same-machine rebuild:** byte-exact.
- **Tests:** the full suite on the final integration branch passed **101 tests in 8 min 16 s** with the threaded solver; it took 20 min 52 s before threading. Main had 103; the integration branch removed 4 old-hedge tests and added 2. The CLI built both files with the §1 hashes, and the threaded 11-origin hedge backtest matches the sequential one exactly (max abs diff 0.0).

## 4. Code state

`origin/main` after the PR #146 merge contains the following. The model behaviour is that of #147 (`9f5da22`) plus the `HEDGE_MODELS` cutover. A later commit in #146 only parallelises the independent per-material MILP solves, and its output is byte-identical:
- `halcyon/submit.py`: `MODELS` is unchanged; `HEDGE_MODELS` uses `policy_scenarios.plan_kes_overlay`.
- `halcyon/events.py`: `plan_shock` was removed. `predict_shock`, `_BAN_WEEK` and `_BAN_CAPACITY` are retained and used by the hedge.
- The hedge invariants (KES floor 0.6 from 224 only; KES requests ≤0.37×normal capacity from 224) moved to `tests/test_submit.py`.
- `halcyon/disruption_fx.py` (fixed), `disruption_scope.py` and `policy_scenarios.py` remain. Only `policy_scenarios.plan_kes_overlay` is live, through the hedge.
- `databricks/pipeline.py` and `tools/databricks/bootstrap.py` import `MODELS`/`HEDGE_MODELS`, so they pick up the new hedge without changes.

Solver note: the hedge uses `scipy.optimize.milp` (HiGHS) with `mip_rel_gap=1e-4` and accepts only status 0 (optimal within the gap). Limits are 900 s, then a 3600 s retry, then raise. `policy_scenarios.plan` solves the 10 independent per-material MILPs in parallel threads; HiGHS releases the GIL. This cut a hedge CLI build from 199 s to 57–67 s on a 10-core machine, with byte-identical output (`cf481a44…` on 2 runs). Each window's time is bounded by its slowest material, at most about 18 s here. AV's pre-threading build took 188 s. Different machines can return different plans that are equally near-optimal (§3 parity). Tightening the gap from 1e-4 to 1e-7 before #147 changed 27 private rows but best-of-two by only −0.0007. A tighter service big-M (currently opening stock + total window capacity) would speed up the hardest solves further but may change tie-breaking, so it was deliberately left for a future, re-selected change.

Known limitation, deliberately **not** fixed: the incumbent `policy._solve` LP allows `served <= demand`. The optimizer can therefore plan to withhold stock to avoid its soft safety-stock penalty, while the simulator always serves `min(stock, demand)`. Andrew found this in the scenario MILP and fixed it there (#141). The incumbent is the preserved champion and was not changed in this run. Any future fix must be selected on the 11 origins like any other model change.

## 5. Next step: refit and final private submissions (human-authorized only)

1. Use a fresh worktree at the `origin/main` SHA recorded in §4. Do not use the stale original checkout or its user changes.
2. Build both files with the commands in §1, then confirm `validate` passes and the CSVs have 260 rows. The **primary** must match `0da997d7…` byte-for-byte. The **hedge** matches `cf481a44…` only on an identical environment (this workstation: Python 3.12.16, scipy 1.18.1, numpy 2.5.4, pandas 3.1.1). Elsewhere, expect a different near-optimal plan. Either upload the canonical file from the gist below, or record the hash of the rebuilt bytes that are actually uploaded. Do not rebuild repeatedly to pick a version.
3. Optional Databricks track: use existing job **838646686083545** only, with an authenticated operator. Never create jobs or change grants. Download both CSVs. The primary must match within 1e-9. A different hedge plan is expected there, so record which hedge file is uploaded.
4. Humans upload and select the two final files. **Preserve the official 70.76 champion** and its original receipt (hash prefix `984a0b19`). The known-byte scope tie file (`scope_honest_20261107T234427Z.csv`, SHA `5af90cd9…`, also official 70.76) stays in draft release `campaign-128`; it is **not** selected.
5. Do not modify either selection based on public leaderboard feedback.

## 6. Things not to repeat

- Scope as a primary: its historical gain is from origin 195.
- Price jump/aggregation and probability residual shrinkage (#143).
- All rejects listed in the campaign-128 record: typed survival, supplier graph, latent price factors, physical price regimes, term-structured landed costs, F/R frontier, warning lifts and flag age. Full evidence is in #129–131 and draft release `campaign-128`.
- More KES/stress hand-tuning. Synthetic gains cannot override historical failure.

Evidence: the canonical final CSVs (primary `0da997d7…`, hedge `cf481a44…`), the per-origin CSV and the S0–S5 stress CSV are in this secret gist: https://gist.github.com/JA-01/3b76742b0cf802c41b06903a30799ccb. Andrew's 13-path stress and scripts are on #141. FX and research results are on #142 and #143.

**SIGN-OFF: Jaseer's Claude (orchestrator) SIGNED OFF. No watchers, jobs, or open assignments remain. Resume only under a new human directive.**
