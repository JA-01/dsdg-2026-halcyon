<p align="center">
  <img src="docs/readme/hero.png" alt="Halcyon by Bay Area Builders: 1st on the private leaderboard at 71.40 and 2nd overall at DSDG Hackathon 2026" width="100%">
</p>

<p align="center">
  <a href="#results"><img alt="Private leaderboard: 1st, 71.40" src="https://img.shields.io/badge/private%20leaderboard-1st%20%C2%B7%2071.40-e5482f"></a>
  <a href="#results"><img alt="Overall: 2nd" src="https://img.shields.io/badge/overall-2nd-15171c"></a>
  <a href="#the-message-board-how-ten-agents-built-it"><img alt="Message board: 570 agent posts" src="https://img.shields.io/badge/message%20board-570%20agent%20posts-6e7781?logo=github"></a>
  <a href="#the-databricks-track"><img alt="Databricks track" src="https://img.shields.io/badge/track-Databricks-FF3621?logo=databricks&logoColor=white"></a>
  <a href="LICENSE"><img alt="MIT license" src="https://img.shields.io/badge/license-MIT-3776AB"></a>
</p>

# Halcyon

This is our entry for **[DSDG Hackathon 2026: Supply Chain Disruptor](https://www.kaggle.com/competitions/dsdg-hackathon-2026-supply-chain-disruptor)**, a Kaggle competition run by the Data Science Development Group at the University of Illinois Urbana-Champaign from November 6 to 8, 2026, with Agentic AI @ UIUC and Databricks.

Halcyon Industries is a fictional manufacturer. It buys 10 raw materials from 6 countries over 5 shipping lanes, and every few months something breaks: a tariff hike, an export ban, a closed strait, a strike. Some shocks show up in the news and the futures market weeks ahead. Some warnings are rumours that never happen. Policy reversals give no warning at all.

A submission is one 260-row CSV, one row per material per week. Each row is both a forecast and a decision: the probability that the material is disrupted, its benchmark price, how many units to order, and how to split the order across supplier countries. A simulator then plays the orders out against what actually happened.

Four of us each ran our own AI coding agents (Claude Code and Codex). **The agents built this planner together, talking to each other on one pinned GitHub issue: [the message board](#the-message-board-how-ten-agents-built-it).** They shared data and compute on Databricks.

## Results

The final private leaderboard scored weeks 222 to 234, which no team could see before the deadline.

| # | Team | Private score |
|:-:|---|--:|
| **1** | **Bay Area Builders (us)** | **71.40** |
| 2 | Rhythm | 70.82 |
| 3 | Risk Takers | 69.69 |
| 4 | IDK | 69.54 |
| 5 | Claude & Em | 68.90 |

Final placement counted the private leaderboard for 80% and a judged three-minute video for 20%. We topped the private leaderboard by 0.58 points and finished **2nd overall, 0.3 points behind first**.

Some other numbers from the weekend:

- **0 to 51.7.** That is our mean score over 11 past 13-week windows. It started at the organizer's naive baseline, which scores 0, and it is a local estimate.
- **70.76 on the public leaderboard (official).** That file forecast weeks 209 to 221 using only data through week 208, so it was a true out-of-sample test.
- **54.10, then 59.** Those were our public scores from the Friday-night attempt before we started over ([why](#two-boards-two-nights)).

## The challenge

```math
\text{Score} = 100 \times (0.30\,P + 0.40\,F + 0.30\,R)
```

| Part | Weight | What it measures |
|---|--:|---|
| **P**, prediction | 30% | Brier skill on `disruption_prob` (60%) and MAPE skill on `price_forecast` (40%) |
| **F**, financial | 40% | Share of the cost gap closed between the naive policy and a plan that knew the future |
| **R**, resilience | 30% | Fill rate during shock weeks compared with naive (70%) and supplier diversification (30%) |

Each part is clipped to 0–1 and scaled so that the naive sample submission scores 0. In the simulator, each window starts with 5 weeks of demand in stock. Holding costs 2% of the landed cost per week, and an unmet unit costs 5 times that cost. Leftover stock sells back at 70%. Phase 1 released weeks 1–208 on Friday evening and Phase 2 released weeks 1–221 at noon on Saturday. Each team selected two final files, and only the better private score counted. The full rules are in [`kaggle_instructions.md`](kaggle_instructions.md).

## The message board: how ten agents built it

<p align="center"><img src="docs/readme/slide-board.png" alt="One pinned GitHub issue was our team chat: 318 posts, 10 agent identities, 101 pull requests" width="100%"></p>

Each of us ran our own agents on our own laptop, and the agents talked to each other on one pinned GitHub issue. An agent posts what it merged, with the number it measured, and tags whoever needs to act by GitHub login; that teammate's agent wakes up, does the work and replies in the same thread. Humans read along, posted directives and handled the Kaggle uploads. Saturday's board is issue [**#75**](https://github.com/JA-01/dsdg-2026-halcyon/issues/75) and Friday's is [**#1**](https://github.com/JA-01/dsdg-2026-halcyon/issues/1).

The setup comes from the [azizu06/hackathon-agent-board](https://github.com/azizu06/hackathon-agent-board) template. Everything the agents ran with is still here, unchanged:

| File | What it does |
|---|---|
| [`tools/board`](tools/board) | The message bus: a bash script around the `gh` CLI with `post`, `unread`, `wait` and `read` |
| [`AGENTS.md`](AGENTS.md) | Team rules every agent reads: post format, when to reply, who owns which files |
| [`CLAUDE.md`](CLAUDE.md), [`.claude/`](.claude/) | Claude Code hooks that surface unread posts at session start and on every prompt |
| [`orchestrator.md`](orchestrator.md), [`worker.md`](worker.md) | The prompts that started the orchestrator and worker agents |

### A real exchange

About 80 minutes before the deadline, Jaseer's orchestrator agent needed every candidate file built and checked. [One post](https://github.com/JA-01/dsdg-2026-halcyon/issues/75#issuecomment-6724132506) split the work between Andrew's and Tejas's agents, and six minutes later all eight files were built and audited:

```mermaid
sequenceDiagram
    participant J as Jaseer's Claude (orchestrator)
    participant A as Andrew's Claude
    participant T as Tejas's Codex
    J->>A: 16:38 FINAL SPRINT. HEAVY: build 4 upload files, then 3 backtests
    J->>T: 16:38 LIGHT: audit the 4 files already on GitHub
    T-->>J: 16:39 Taking the LIGHT audit
    A-->>J: 16:40 (A) done, 4 files pushed to final-v3-minimax
    T-->>J: 16:40 Audit PASS, 4 of 4
    J->>T: 16:41 Same checks on Andrew's 4 new files
    A-->>J: 16:41 (B) done, 11-window backtests posted
    T-->>J: 16:43 Audit PASS, all 8 files checked
    J->>J: 16:44 FINAL SPRINT COMPLETE, signs off
```

### Two boards, two nights

Our first attempt on Friday night failed. Our [coroner's report](coroner/CORONERS_REPORT.md) found the agents spent about 4 hours on release machinery and cross-checking each other's hashes, left the prediction component at zero, and ended the night waiting on each other. On Saturday we started over (the old code is on the `archive/phase1-v1` branch) with four rules: build the scorer first, one orchestrator with one owner per file, label every number "local estimate" or "official", and nobody waits.

| | Friday, board [#1](https://github.com/JA-01/dsdg-2026-halcyon/issues/1) | Saturday and Sunday, board [#75](https://github.com/JA-01/dsdg-2026-halcyon/issues/75) |
|---|---|---|
| Who coordinates | Command changed hands four times | One orchestrator agent at a time |
| Posts that say ACK | 58 of 251 | 6 of 319 |
| When blocked | Wait for the next post | Post the blocker and switch tasks |
| Result | 54.10 public, then a deadlock | 70.76 honest public, 1st on the private leaderboard |

To run a board on your own project, start from the [template](https://github.com/azizu06/hackathon-agent-board) and point `BOARD_ISSUE` at your own pinned issue (the default here is 75, our board).

## How the planner works

<p align="center"><img src="docs/readme/slide-pipeline.png" alt="Four stages, each one swappable: signals, forecasts, order plan, two submissions" width="100%"></p>

`halcyon/` is one small Python package with **one module per lever and one frozen function contract per module**. Every module started as the organizer's naive reference, and a test showed that `main` reproduced `sample_submission.csv` exactly. From then on, each improvement replaced one function, and we measured it before it went in. On two of the stages, two teammates built competing versions against the same contract, and the winner went live through `submit.MODELS`.

| Stage | Module | What it does |
|---|---|---|
| Point-in-time data | [`data.py`](halcyon/data.py) | `as_of(tables, cutoff)` cuts every weekly table at the cutoff, so no model can see the future |
| Disruption probability | [`disruption_news.py`](halcyon/disruption_news.py), [`disruption.py`](halcyon/disruption.py), [`strategy_expected.py`](halcyon/strategy_expected.py) | State persistence, a news warning ladder, a futures-basis hazard and announced tariffs |
| Price | [`price.py`](halcyon/price.py) | Slow reversion toward the 104-week mean, plus price steps when the futures basis flags a capacity shock |
| Orders (primary) | [`policy.py`](halcyon/policy.py) | A per-material linear program over the 13-week window that mirrors the simulator's costs |
| Orders (hedge) | [`policy_scenarios.py`](halcyon/policy_scenarios.py) | A scenario MILP (HiGHS) that plans one set of orders against several shock paths |
| Assembly | [`submit.py`](halcyon/submit.py) | Builds and validates the 260-row file using the organizer's rules |
| Scoring | [`score.py`](halcyon/score.py), [`stress.py`](halcyon/stress.py), [`scenarios_p2.py`](halcyon/scenarios_p2.py) | Local P/F/R scorer with a hindsight LP, plus synthetic stress tests for the private window |

### Signals we trusted

<p align="center"><img src="docs/readme/slide-signals.png" alt="6 of 6 futures signals, 8 of 9 country-and-material warnings, 3 of 3 announced tariffs" width="100%"></p>

- **Futures basis.** A supplier's onset followed 6 of 6 times, with no false alarms and a median lead of 3 weeks, whenever `futures_4w / spot − 1` went above 5% (or stayed above 3.5% for two weeks). Read-only exploration subagents found this halfway through Saturday. It then held out of sample on lithium, which was flagged at week 209 and hit at week 215.
- **News warning ladder.** The 4,317 articles reuse just 231 headline templates. We map each template to a place (a country or a lane), a shock family and a stage: early, imminent, event, averted or recovery. A story that names a country applies only to the materials that country sells. Warnings expire after 4 weeks without a repeat. Hit rates per family are learned with shrinkage, which pushes decoy-heavy families down. This model was our largest single gain: on the held-out window, P went from 0.07 to 0.32.
- **Announced tariffs.** The label rule is exact (it matches 2,210 of 2,210 rows): a material counts as disrupted when any supplier has under 90% of normal capacity, a lead time above base, or a tariff above base. That makes a published tariff hike a disruption from its effective week, and all three announced campaigns in the history took effect.
- **Persistence.** Disruptions are sticky, with a median of 8 weeks per episode. The base model learns P(disrupted at *t + h* | state, age).

Several ideas were tested and dropped: country-tension and lane-congestion flags, calibration curves, source credibility and cues from article bodies. Prices behave close to a random walk, and about ten alternatives (momentum, averages, futures blends) failed to beat the last price.

### From forecast to order

The LP plans each material over the window with the simulator's own economics. It keeps 1.75 weeks of safety stock, and a convex sourcing cost spreads orders across suppliers whose prices are close. **A supplier flagged by the futures basis is planned as an export ban**: 5% capacity for 8 weeks, starting 2 weeks after the first flag. That way, orders move to the other two suppliers before the shock. A score-aware rebalance then moves share to cheap-enough peers when the diversification points outweigh the cost points. Rows with no order get even shares, which earns diversification at no cost.

## Keeping ourselves honest

| Set | Weeks | Use |
|---|---|---|
| **Selection** | 11 rolling origins (cutoffs 65, 78, …, 195), each scoring the next 13 weeks from data up to the cutoff | Every model and parameter choice. We reported the mean and the worst origin |
| **Held-out** | 209–221, planned from week 208 | Scored once per merged change and never tuned on. The public leaderboard gave an official score for this window |
| **Final refit** | 222–234, planned from week 221 | Same code, refit on all released data |

A test asserts that the public rows match a pure week-208 build. We checked the scorer against two official scores from the earlier files (52.78 locally vs 54.10 official, and 58.36 vs 59). That check also settled an ambiguous rule: opening stock is 5 times the first week's demand.

These were the main changes on Saturday (times in UTC):

| Time | Change | 11-window mean (local) | Public (official) |
|---|---|--:|--:|
| 16:34 | Naive skeleton on `main` | 0 | |
| 16:48 | Per-material LP policy | 42.3 | |
| 16:53–16:59 | Tapered safety stock, then a convex sourcing cost | 48.8 | |
| 18:25 | Phase 2 data lands, scorer checked against official scores | | 60.75 |
| 18:47 | News warning ladder goes live | 49.6 | 68.96 |
| 19:48 | Futures-basis hazard, export-ban planning, price steps | 51.1 | |
| 20:30 | Score-aware rebalance | 51.63 | |
| 21:23 | Warning shrinkage | 51.68 | **70.76** |

## Two final files, best of two

Only the better private score of the two selected files counted, so we chose two files that do well in different futures instead of two similar ones.

- **T, the primary.** The champion model with one extra rule: a material is held at a disruption probability of at least 0.917 from the effective week of an announced tariff hike. `python -m halcyon.submit --released-public` rebuilds the uploaded file byte for byte (SHA-256 `5f77482f…`).
- **SCEN_T, the hedge.** The same forecasts, but the orders come from the scenario MILP. It learns capacity and lead-time paths from completed historical shocks and plans one set of orders that holds up across all of them. On its own it scores lower (49.4 vs 51.7 over the 11 windows), because it over-insures calm windows. Next to T it adds 2.3 points to the historical best-of-two, all from the two big shock windows (+22.3 at cutoff 169, +3.2 at 104).

In the final hour we also built country-specific variants of the hedge, betting on a Kestria export ban (H_T) or a Valdmar collapse (VAL_SCEN), and ranked every pair on a 19-scenario matrix of possible private windows. At the deadline we went with SCEN_T, the scenario policy without a country-specific bet. All eight candidates and how to rebuild them are in [`submissions/`](submissions/).

After the Phase 2 release, the public weeks were already known, so both uploaded files fill weeks 209–221 with the released outcomes (`--released-public`). This cannot change the private score. Our honest public result is still 70.76.

One lesson stood out. A plan built for the "expected" future won our own scenario matrix (76.79), but it lost 11 points on the one real Phase 2 window (60.35 vs 71.36). We rejected it, because scenarios we wrote ourselves cannot overrule real outcomes. [`handoff.md`](handoff.md) records every candidate, hash and rejected alternative.

## The Databricks track

<p align="center"><img src="docs/readme/slide-databricks.png" alt="Every agent reads the same truth: 26 Delta tables, 9 strategies as serverless jobs, 32 MLflow runs, cloud-to-local gap of 2e-11" width="100%"></p>

| Piece | Where |
|---|---|
| Ingest | [`tools/databricks/bootstrap.py`](tools/databricks/bootstrap.py) packages the **committed** `halcyon` code and `data/*.csv` into a Unity Catalog Volume |
| Delta | [`databricks/pipeline.py`](databricks/pipeline.py) reads the 10 CSVs with explicit schemas ([`schemas.json`](databricks/schemas.json), FAILFAST) into versioned `c2_*` tables |
| Compute | A serverless job builds and validates both final files from those tables |
| MLflow | Each run logs the source revision, cutoffs, metrics and both CSVs |
| Bundle | [`databricks/databricks.yml`](databricks/databricks.yml) is an Asset Bundle that follows the organizers' example |
| Extras | [`headline_demo.py`](databricks/headline_demo.py) runs `ai_classify` on headlines in SQL; the `*-results.md` files hold the price and policy-challenger backtests |

The data is small, about 6,000 rows per table, so development and backtesting ran locally in a 10-second loop. Databricks was the reproducible, auditable build of `main`, and every cloud build matched the local one to within 2×10⁻¹¹. We chose Delta over a plain bucket because when ten agents share data, conflicting writes fail cleanly instead of the last write silently winning. Unity Catalog proved the point: it refused a job that tried to overwrite tables owned by another teammate. Details are in [`tools/databricks/README.md`](tools/databricks/README.md).

## What our approach would miss

- **Policy reversals.** No signal warns of them, so no forecast sees them coming.
- **Small samples.** We had 6 futures events, 3 tariff campaigns and 1 strait closure. Several caps (the 0.85 tariff probability, the 37% capacity haircuts in the overlay hedges) are documented judgment calls.
- **Calm windows.** If nothing breaks, about 21 points of shock-week fill are out of reach for every team.
- **The public gap.** Rhythm led the public window (74.30 vs our honest 70.76), and we never explained that gap. On the private window, the order flipped.

## Run it

```sh
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"

python -m halcyon.score                                    # 11-window backtest, about 10 s
python -m halcyon.submit --out primary.csv                 # primary file (T)
python -m halcyon.score --file primary.csv --start 209 --end 221   # held-out public window
python -m halcyon.submit --hedge --out hedge.csv           # Kestria-ban hedge (H_T), under 1 min
python -m halcyon.stress                                   # synthetic private-window stress test
pytest -q                                                  # full suite; MILP tests take several minutes
```

The primary file is byte-reproducible. The SCEN_T hedge is a one-line model tuple, shown in [`submissions/README.md`](submissions/README.md). The MILP accepts any plan within 0.01% of optimal, so another machine can return a different, equally good plan; the exact uploaded bytes are in [`submissions/`](submissions/).

To run the Databricks pipeline against your own workspace, copy [`.env.example`](.env.example) to `.env`, fill in `DATABRICKS_HOST`, sign in with `databricks auth login`, and follow [`tools/databricks/README.md`](tools/databricks/README.md). Nothing else needs credentials.

## Repository map

```text
halcyon/                                  the planner
  data.py naive.py                        point-in-time data, organizer's naive baseline
  disruption*.py events.py                disruption probability models and challengers
  price.py                                price forecasts
  policy.py policy_scenarios.py           LP ordering policy, scenario-MILP hedge
  score.py stress.py scenarios_p2.py      local scorer, stress tests, private scenario matrix
  submit.py public_max.py                 final CSV assembly
  strategy_*.py policy_challenger.py      Phase 2 candidates and challengers, kept for reference
tests/                                    pytest suite
data/                                     the competition's synthetic dataset
submissions/                              every final candidate CSV, with hashes
databricks/                               notebook job, asset bundle, backtest results
tools/board                               the message board CLI
tools/databricks/                         Databricks bootstrap
presentation/                             the 3-minute video deck (open slides.html, or slides.pdf)
docs/                                     architecture, competition docs, Databricks notes (index in docs/README.md)
coroner/                                  postmortem of the Friday-night attempt, with its board transcript
AGENTS.md CLAUDE.md .claude/              the rules and hooks every agent ran with
orchestrator.md worker.md                 the prompts that started the agents
summary.md                                full record of the Saturday run
handoff.md                                final selections, hashes and rejected candidates
kaggle_instructions.md                    the competition's rules and data description
```

Tags `final-pair-v1` and `final-pair-v2` mark the two earlier final pairs.

## Team

| Who | Built |
|---|---|
| **Jaseer** ([@JA-01](https://github.com/JA-01)) | News warning-ladder disruption model, price model, Databricks pipeline, greedy policy challenger; set up the message board; orchestrated the last two runs |
| **Andrew** ([@andrewkwon0804-web](https://github.com/andrewkwon0804-web)) | Local scorer, LP ordering policy, stress test, scenario-MILP hedge and its audits |
| **AV** ([@AV-01](https://github.com/AV-01)) | Architecture and integration, futures-basis hazard, final builds, FX sanctions challenger; orchestrated Saturday's main run |
| **Tejas** ([@tbhojo](https://github.com/tbhojo)) | Disruption state model, event parsing and shock hedge, cutoff-safety audits, private-window situation reports |

Thanks to the DSDG team at UIUC, Agentic AI @ UIUC and Databricks for running the event.

## License

The code is released under the [MIT License](LICENSE). The message-board tooling (`tools/board`, `.claude/hooks/`, the board issue template and the skeleton of `AGENTS.md`) comes from [azizu06/hackathon-agent-board](https://github.com/azizu06/hackathon-agent-board). The data in [`data/`](data/) is the competition's synthetic dataset from the DSDG Hackathon organizers.
