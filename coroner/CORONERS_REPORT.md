# Coroner's report: `JA-01/DSDG-Hackathon` (Halcyon, Bay Area Builders)

Subject: the Phase 1 repo for the DSDG Hackathon 2026 "Supply Chain Disruptor" Kaggle competition, Databricks track.
Time of death: Fri Nov 6, 23:29 CT, at the board post titled "DEADLOCK FIX / STAND DOWN".
Sources: the message board (GitHub issue #1, 250 posts, saved here as `message-board-issue1.md`), every `.md` file in the repo, `docs/agents/*`, git history (85 commits, 41 PRs), MLflow artifacts saved in `/tmp/orch`, and a re-analysis of `data/` and the submitted CSVs.

---

## 1. Verdict

**Cause of death: process asphyxiation.** Four AI agents, each run by a different human, built a release pipeline with heavy provenance checks. It was mostly done before there was anything worth releasing. The first Kaggle score (54.10) used none of the Prediction component. U2 was uploaded after the original postmortem and scored **59**, a 4.9-point improvement. Every change before U2 had been kept "bounded" to a sliver of the problem. The night ended with every agent waiting on every other agent.

Contributing factors:

1. **Infrastructure before signal.** In ~4 hours the team built Databricks/Delta/MLflow ingestion, SHA-pinned manifests, release acceptance, Phase 2 archive tooling, a demo notebook and a 185 s synthetic-voice video. The video was rendered at 20:38 CT, before any model had been selected. The forecasting models in the scored file are a historical mean and a last-price carry-forward.
2. **Prediction (30% of score) initially left at exactly zero.** The 54.10 file's `disruption_prob` matches the organizer's naive `sample_submission.csv` to within 4.6e-5. Its `price_forecast` is byte-identical. Both are scaled so the naive file scores 0, so P = 0.
3. **Governance overhead.** The board has 250 posts and 22k words. It contains 55 ACK posts, 30 sign-off mentions, 21 HOLD mentions and 21 corrections or retractions, plus ~30k words of planning docs. That is against 3.2k LOC of package code and 2.7k LOC of tests. Agents spent most of their effort cross-verifying each other's byte hashes, not improving score.
4. **The only oracle was used too late.** The public leaderboard (weeks 209–221, 5 uploads/day, meaningful until Sat noon) was used once during the active session. The V2 candidates U1 and U2 were built and verified but not uploaded before the team stood down. U2 was uploaded later and improved the public score from 54.10 to 59.
5. **Self-imposed paralysis.** "No tuning", "no new models", "holdout locked", "bounded change only" and "owner must ACK" were repeated as rules. The V2 cycle produced only small deltas on top of the incumbent.
6. **Role churn.** Command moved from Jaseer (lead) to Andrew (integration lead), then to "peers, nobody orchestrates", then to Jaseer's lead decisions, then to AV's agent as orchestrator. One forecasting takeover and handback took 60 seconds and changed zero files.

---

## 2. Timeline (Fri Nov 6, Central)

| Time | Event |
|---|---|
| 17:31 | First commit (before the 18:30 data release) |
| 18:43 | Jaseer's agent profiles the data. It recommends CatBoost, event extraction, a HiGHS optimizer and fixed-origin backtests. CatBoost was never shipped; the only trace is a tracked `catboost_info/` folder |
| 19:00–19:21 | Databricks requirements doc, workspace provisioning, 10 bronze + 2 silver Delta tables, MLflow smoke test |
| 19:27–19:44 | Ownership rebalanced to save Jaseer's tokens. Plan and contracts merged (PR #15) |
| 20:21 | AV: simulator + `InventoryPolicy` merged (PR #19) |
| 20:22 | Andrew: contracts/scaffold and first real Delta run |
| 20:24–20:27 | Tejas's agent marked offline. AV takes forecasting; Tejas returns 1 minute later; handback with zero files changed |
| 20:32–20:41 | Baseline forecaster merged. Pooled ExtraTrees **rejected** (Brier worse in 3 of 4 dev blocks). Price-only variant merged as an option |
| 20:38 | Demo + 185 s video produced. 20:43, human: "don't worry about the video" |
| 20:44 | AV: `OptimizedPolicy` (HiGHS MILP) merged |
| 20:51–20:56 | Humans ask agents to define the "MVP". All four agents post near-identical definitions |
| 20:57 | Frozen selection: historical forecast + optimized policy. Holdout 182 evaluated once at 20:58 |
| 21:06 | "NEW SUBMISSION CSV" (`2240be82…`) |
| 21:09–21:11 | AV's agent closed; Jaseer's role handed to Andrew; Tejas's agent offline. Andrew is the only agent left |
| ~22:08 | **Kaggle public score 54.10** reported for `2240be82…`. V2 starts |
| 22:08–22:45 | Four V2 review docs (~48 KB). Proposals flip-flop: cost tilt rejected, then approved; price blend deferred, then approved |
| 22:27 | Jaseer HOLD. At 22:32 Andrew's agent, whose board watcher had lapsed, posts a release and sign-off, then retracts |
| 22:33 | Human, in caps: "YOU GUYS ARE NOT UPDATING CODE, YOU ARE FINDING AND REACHING AGREEMENTS" |
| 22:39 | HOLD released; final V2 list (9 items). At 22:41, human: "agree on a final list of improvements **to implement later**". At 22:48 Andrew's agent posts U2 anyway |
| 22:56–22:59 | All agents relaunched as "workers"; AV's agent declares itself orchestrator and files issues #64–#70 |
| 23:00–23:15 | Upload U1/U2 ordered, then retracted, then banned until "PIPELINE COMPLETE" after Phase 2 |
| 23:28 | AV's agent: "DEADLOCK FIX… every agent is watching for the next step… watchers are just waiting on each other." Everyone stands down |

---

## 3. What was built

`halcyon/` package, 3,185 LOC:

| Area | Modules | LOC | Notes |
|---|---|---:|---|
| Modeling: forecast | `forecasting/{baseline,models,features}.py`, `news/{extract,signals,forecaster}.py` | ~690 | Historical rate/last price; pooled ExtraTrees (rejected); news template extraction + `DisruptionModel` |
| Modeling: policy/sim | `policy.py`, `simulator.py`, `baselines.py` | ~960 | Naive, inventory-cover heuristic, per-material MILP with lane penalty + optional `cost_tilt`; pandas simulator |
| Infra/release | `pipeline, contracts, data, submission, accept, compare, delta, deploy, phase2, spark, testing, constants` | ~1,530 | Point-in-time `Dataset.as_of`, validator, SHA manifests, Delta/MLflow, Phase 2 public-archive logic, Spark feature parity |

Also present: 2,717 LOC of tests (379 passing), `tools/databricks/` provisioning, `tools/board` (a GitHub-issue message bus with Claude hooks), and 17 markdown docs. Of those docs, about 12 are process, Databricks or release material and about 3 cover modeling.

**Algorithms in the scored file:**
- `disruption_prob`: each material's mean `disrupted` through week 208, flat across all 26 weeks. This equals the naive reference.
- `price_forecast`: last benchmark price at week 208, flat. Identical to the naive reference.
- `order_units`: a per-material MILP that plans each 13-week window independently. Inputs are trailing-13-week supply estimates (capacity q25, lead time q75) and a buffer of 2 + 2×risk weeks; stockouts carry a penalty. 45% of rows order 0 because of the 5-week opening stock and end-of-window salvage. 52% of order quantities are fractional. Total orders are 61% of demand.
- Shares: lane-balanced across eligible suppliers with an L1 lane penalty. Mean HHI is 0.34, so diversification is about 0.99.

---

## 4. Strategies tried and verdicts

| Idea | Owner | Evidence | Verdict |
|---|---|---|---|
| Historical rate + last price | Tejas | Equals the naive reference | Shipped. **P = 0 by construction** |
| Pooled ExtraTrees (42 numeric features, multi-horizon) | Tejas | Brier 0.529 vs 0.189 (origin 130, h1–13); 0.705 vs 0.088 (130, h14–26); wins only at 156 h1–13 | Rejected. Origin 130 sits inside a 35-week shock that dominates training |
| Pooled price regressor (log-return) | Tejas | Dev MAPE 0.0723 vs 0.0735, but h1–13 regresses (0.0647 → 0.0661). Andrew's estimator: price skill −0.12 | Runner-up file built (`dbf562db…`), never uploaded, dropped |
| Pooled logistic disruption | Andrew | Hit 0.87 Brier at h26 | Abandoned |
| News state-lift `DisruptionModel` (66 headline templates, shrunk lift over material rate, h ≤ 13) | Andrew | Raw Brier skill +0.207 (7/9 origins, Tejas's independent check); estimator ≈ +4.5 P-points. Andrew: current-state conditional skill +0.32 (h1–4), +0.10 (h5–8), −0.02 (h9–13) | Shipped in U2 as one part of the 59-point result |
| Inventory-cover heuristic | AV | Beats naive in 3 of 4 dev windows; −0.96% regression in one calm window | Superseded |
| MILP `OptimizedPolicy` | AV | −3.07% summed proxy cost vs heuristic; fill up in 4/4 windows. Holdout (calm): −1.5% / −0.5% vs baseline, fill slightly *below* naive | **Shipped in 54.10** |
| Uniform shares on zero-order rows | AV | Diversification +0.0058 per window; nothing else changes | Shipped in U2 as one part of the 59-point result |
| Post-hoc cost tilt `exp(-k·rel_cost)`, k = 3, + `risk_buffer_weeks` 4 | Andrew → Jaseer | Estimator +3.07 mean, worst −6.47, 15/19 wins; +4.80 calm vs +0.69 shock. Origin 97: cost 5.56M → 6.20M, shock fill 0.923 → 0.863 | Shipped in U2 as one part of the 59-point result |
| 75/25 last-price / 52-week-mean blend | Andrew | +0.34 P-points, 16/19 positive | Shipped in U2 as one part of the 59-point result |
| In-MILP tilt; lower `diversification_penalty` | Jaseer | +3.2 mean but worst −13.0 / −26.8 | Rejected |
| Higher base buffer; rounding; tariff-aware costs; LLM news; CatBoost | various | Negative or untested | Dropped |

**Estimator caveat.** Every V2 estimate comes from `estimate.py`, a throwaway re-implementation of the published formula. Andrew and Jaseer each implemented it, and the two agree. It was not calibrated against Kaggle before U2 was built. Its windows (origins 52–169) overlap dev data. The local incumbent scored 36.7 / 31.5 against 54.10 on the real public window. U2's later score of 59 validates the combined direction, but the leaderboard result does not isolate the contribution of any one change.

---

## 5. Scoreboard

| File | SHA-256 | Content | Public score |
|---|---|---|---|
| V1 incumbent (MLflow `7d227194…`) | `2240be824b08…aead6` | historical + MILP | **54.10** |
| V2 U1 (`32244c21…`) | `59dc988ba37d…5f07e3` | V1 + news probabilities on 130 public rows + zero-order uniform shares. Orders and prices identical to V1 | none recorded |
| V2 U2 (`013655b7…`) | `9c59e2bcdd5d…6440b` | U1 + 75/25 last-price / 52-week-mean blend + cost tilt k=3 + risk buffer 4. 137 rows change units | **59** |
| Runner-up (`5ef4cf17…`) | `dbf562db7758…15b0` | pooled price + MILP | never uploaded |
| Earliest fallback (`74752ffe…`) | `734c30db0566…1247` | inventory heuristic | never uploaded |

U2 improved the public score by **4.9 points** over V1. Relative to V1, it combined four modeling/policy improvements: news-conditioned disruption probabilities, uniform supplier shares on zero-order rows, a 25% blend toward the 52-week mean price, and cheaper-supplier cost tilt with the risk buffer raised to four weeks. Because these changes were submitted together, the leaderboard result cannot attribute the gain among them.

### What 54.10 tells us

With P = 0, `54.10 = 40·F + 30·(0.7·fill_skill + 0.3·div)`. On the public rows div ≈ 0.989, so `40F + 21·fill_skill ≈ 45.2`. That gives **F ∈ [0.60, 1.0] and fill_skill ≥ 0.25** on weeks 209–221. For the new team:
- **There are about 30 points of P on the table.** Even modest Brier/MAPE skill adds points directly. P is clipped at 0, so a file that equals the naive reference cannot lose points on P [conditional on the organizer's reference being the historical rate at the release cutoff; unverified for Phase 2].
- **R's diversification term is already maxed** (~9 points). Further R gains come only from shock-week fill.
- **F is the 40-point lever.** In the local estimator, the incumbent policy closes only 16–22% of the naive→hindsight cost gap in calm windows (origins 52–84). It is *worse than naive* in origins 136 and 149 (raw F −0.75 and −0.38, clipped to 0). The public window happened to be kind to it.

---

## 6. Defects and loose ends found by the team

- Validators int-cast fractional weeks (209.5 → w209). Fixed in PR #38.
- First news config changed private h14–26 probabilities (max 0.017). Fixed in PR #54.
- Phase 2 acceptance checked the archived public block only when given an explicit flag. Fixed in PR #51.
- `accept` never reads cutoff, release or config, so a stale run ID can pass. Covered in the runbook, not in code.
- `phase2.py` names configs by release only, so a second slot overwrites the first unless you pass `--output`.
- Unknown simulator rules, never resolved because the organizer starter notebook was never obtained: cost reference for holding/shortage/salvage, opening stock (5× first week vs sum of first 5 weeks), whether fractional orders are allowed, whether F/R are aggregated per material or per window, and whether diversification counts zero-order rows.
- Unverified assumption that "best of the 2 selected submissions counts" on the private leaderboard. The U1/U2 hedge depends on it.
- Repo hygiene: `catboost_info/` and `.DS_Store` are tracked, and the `.gitignore` regression briefly un-ignored `artifacts/`.

---

## 7. Process autopsy

| Pattern | Evidence |
|---|---|
| Ownership bureaucracy | Editing another owner's file needed a board request plus ACK. The week-key fix took 4 posts to hand off and 2 to hand back |
| Verification theatre | The same CSV hash was independently re-downloaded and re-validated by 3–4 agents. The "Spark parity" and "artifact acceptance" harnesses had no effect on score |
| Agents posting for agents | Posts are dense with IDs, hashes and board-comment references. A human asked for a ✅ convention and for the literal phrase "NEW SUBMISSION CSV" because "my eyes glaze over jargon" |
| Premature sign-offs | AV, Andrew and Tejas each signed off, then were pulled back. Andrew released during a HOLD he hadn't seen |
| Conflicting human directives | "Upload U1 now" was followed by "NO uploads", then "no uploads until pipeline complete", then "GitHub OK, Kaggle banned". There was also "agree on improvements to implement later" vs U2 already being built |
| Identity confusion | AV's agent posted as Tejas; Andrew's agent posted as "Ambre's Claude" |
| Coordination deadlock | Every remaining task waited on Phase 2 data or another agent's post, and all watchers waited on each other |

**What actually worked:**
- Leakage-safe `Dataset.as_of` with future-mutation tests.
- An honest negative-results culture: pooled models were rejected on evidence.
- A real, tested MILP.
- An independent check that caught two real boundary bugs.
- A working local P/F/R estimator, including a hindsight LP.

---

## 8. Leads for the new repo

These are observations from the old repo and data, not tested plans.

1. **Start with a scorer, not a pipeline.** `bundle/scorekit/calibrate.py` scores any 260-row CSV for a realized window with full P/F/R, using the sample file as naive and a hindsight LP. It runs standalone from the bundle; mechanics were smoke-tested. At Sat noon the Phase 2 release puts the truth for weeks 209–221 in the data. Re-score the 54.10 file locally first: that is the first real calibration of any local estimator.
2. **Disruptions are long and persistent.** There are 31 episodes in weeks 1–208, median 8 weeks, mean 13, max 35. The overall rate is 19.4%, ranging from 3.8% (copper) to 33.7% (rare earths). If a material is disrupted at the cutoff, the near-term weeks should be close to 1. At cutoff 208 nothing was disrupted (weeks 200–208 all 0), which is why state models barely moved the public rows. Cutoff 221 may differ.
3. **News is templated.** There are 4,317 articles but only 231 unique headlines. Only 21% name a material; the rest name countries, lanes or ports. Closures and strikes hit every country on a lane at once, and the label is "any of the 3 suppliers hit". So model shocks at supplier/lane level, then aggregate to material. `bundle/reference/news_extract.py` has 66 mapped templates as a starting point.
4. **Price skill is cheap but small.** Futures added no skill (Andrew). A 25% blend toward the 52-week mean gave +0.34 points. Tariff announcements exist on only 30 rows.
5. **F upside is large.** The current policy closes only ~20% of the cost gap in calm weeks and loses to naive in some shock windows. The hindsight LP shows the target structure: buy from the cheapest supplier with capacity, time arrivals just ahead of demand, and salvage at 70%. Diversification is worth at most 9 points total, while each +0.1 of F is worth 4 points, so trading some diversification for cost can pay.
6. **Use the public board before Sat noon.** U1 and the incumbent differ only in public-row probabilities, so uploading U1 directly measures what the news model is worth on P. After Sat noon the public board is meaningless; use the local re-score instead.
7. **Process.** Use one score owner, with a local scorer before any infrastructure. Make leaderboard probes a scheduled resource. Have at most one agent coordinate, and keep the board for humans.

### Hard deadlines still ahead (Central)
- **Sat 12:00**: Phase 2 data (weeks 1–221). Re-plan the private window with a cutoff of 221.
- **Sat 18:00**: Databricks track opt-in closes. A fresh repo that drops Databricks forfeits the track. The workspace `workspace.halcyon` and `tools/databricks/bootstrap.py` still exist if you want to keep it.
- **Sun 12:00**: select 2 final submissions and upload the ~3-minute video to the team Drive folder. Kaggle defaults to your 2 best public scores if none are selected.
