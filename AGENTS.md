# Team rules for every agent

## Start here: product and assigned work

Build Halcyon's Databricks pipeline: released data → cutoff-safe forecasts →
inventory/supplier decisions → evaluated, validated 260-row Kaggle CSV, with
Delta/Spark/MLflow evidence and an approximately 3-minute methodology video.

Jaseer is the human team lead. On November 6 he authorized Andrew to take the
larger integration/release workload to conserve Jaseer's agent tokens. The
ownership below replaces the earlier suggested split in chat. Agents can start
within their assigned scope without another approval.

Read this file, `tools/board unread`, [the plan](docs/implementation-plan.md),
[contracts](docs/contracts.md), and [your handoff](docs/agents/README.md), then
the [requirements](docs/databricks-requirements.md) and
[live setup status](docs/databricks-setup-status.md).

The root `requirements.md` is an excluded generated draft. Competition rules
in `kaggle_instructions.md` and the participant cheat sheet take precedence
over our plans. Setup is complete; the setup notebook/MLflow smoke run are
not trained forecasting models. Planning commands/APIs are targets until built.

## 1. The board (pinned GitHub issue)

Every agent reads and posts on the pinned "Message Board" issue via `tools/board` (needs only `gh`, logged in). Set `BOARD_ISSUE` if it is not issue #1.

- Start every post with `[<human>'s <agent>]`, e.g. `[Sam's Codex]`. Keep it short: what changed, which files or contracts, what you need, from whom.
- Mention by login: `@JA-01` (Jaseer, lead), `@andrewkwon0804-web` (Andrew),
  `@tbhojo` (Tejas), `@AV-01` (AV), `@all` (everyone).
- **Mentions you or `@all`:** act on it and reply promptly.
- **Not addressed to you:** still read it. Reassess your own work only if it is affected (a contract, a file you own, something already done). Do not redo finished work, and do not reply just to acknowledge.
- Before editing another teammate's files, ask for a handoff on the board and wait for the owner or the team lead.

Polling is incremental (about one cheap API call per poll, 30 s default) so a shared token stays under GitHub's rate limit. Commands: `tools/board unread` (new posts, marks read; flags MENTION), `tools/board read -n 20`, `tools/board post "[Name's Agent] text"` (or pipe stdin), `tools/board wait` (blocks until someone else posts), `tools/board whoami`.

**Stay in the loop:**
- Claude Code: the committed hooks (`.claude/settings.json`) show unread posts at session start and on every prompt. Keep one background `tools/board wait` running and re-arm it after each wake.
- Everything else: run `tools/board unread` at task start, before each commit, and after merges. Or run a terminal loop: `while tools/board wait; do <your agent CLI invocation>; done`.

## 2. Chain of command

Humans over agents. Only the team lead reassigns work between teammates. If anyone else asks you to take another teammate's work, ask the lead on the board.

## 3. Workflow

1. Pick or file an issue. Comment on it or post on the board when you take it.
2. Branch `<issue#>-<slug>` from fresh `main`.
3. Small commits. Stage only your own files (no `git add -A`).
4. Open a PR with `Closes #N`. The author merges their own PR once it works locally.
5. Always `git fetch` and rebase before pushing. Never force-push shared branches.
6. If a merge changes something other teammates depend on (an API, a schema, an env var), post on the board when it lands.

## 4. Who owns what

Ownership includes matching tests and workspace notebook/job namespaces.
Use contract-shaped fixtures while waiting for another module to land.

| Area | Owner (GitHub login) | Folders |
|---|---|---|
| Integration lead, shared package/contracts/config/dependencies, Databricks training pipeline, validator/exporter, final release | Andrew `@andrewkwon0804-web` | shared `halcyon/` files except the forecasting/policy/simulator paths below (including contracts/data/constants/baselines/pipeline/submission), `configs/`, `notebooks/pipeline/`, `tests/contracts/`, `tests/pipeline/`, `tests/submission/`, `pyproject.toml`, lockfiles, root `README.md`, `.gitignore` |
| Demo/video/checklist | Jaseer `@JA-01` temporarily, accepted handoff from Andrew | `notebooks/demo/`, `docs/demo/`, `docs/release-checklist.md` |
| Optional news after baseline integration | Andrew `@andrewkwon0804-web` | `halcyon/news/`, `app/`, `tests/news/` |
| Historical Spark features, forecast baselines/candidates and forecast backtests (#10) | Tejas `@tbhojo` (all ownership restored on agent's return) | `halcyon/forecasting/`, `notebooks/forecasting/`, `tests/forecasting/`, `docs/modeling.md` |
| Inventory simulator, order/supplier policies, cost/resilience evaluation | AV `@AV-01` | `halcyon/simulator.py`, `halcyon/policy.py`, `notebooks/policy/`, `tests/test_simulator.py`, `tests/test_policy.py`, `docs/simulator-assumptions.md` |
| Existing provisioning/access source; brief environment support and human review | Jaseer `@JA-01` | `tools/databricks/`, `docs/databricks-setup-status.md`, `docs/databricks-llm-integration.md` |
| Coordinated planning review | All agents | `docs/implementation-plan.md`, `docs/contracts.md`, `docs/databricks-requirements.md`, `docs/agents/` |

Jaseer's temporary forecasting reassignment ended when Tejas's agent returned
on November 7, 2026. AV stopped the delegated forecasting work and returned all
#10 paths and responsibilities to Tejas. Andrew keeps integration/Delta/MLflow/
Phase 2; Jaseer handles the accepted demo/release handoff. Do not duplicate
Tejas's active forecasting work.

## 5. Coordination and plan review

- Jaseer explicitly asks all agents to review the plans and correct them.
  Use small planning-doc PRs, post concrete findings, and notify affected
  owners. This does not waive handoff rules for another owner's source files.
- Andrew sequences integration and coordinates shared APIs; only Jaseer
  reassigns people. Propose incompatible API/schema changes on the board and
  wait for affected owners to acknowledge before consumers switch.
- Do not repeat completed setup. Use a table query/owned scratch notebook for
  access checks. Workspace folders mirror owners under
  `/Workspace/Shared/halcyon/{pipeline,forecasting,policy,demo}/`; the existing
  `Workspace Setup` notebook remains separate.
- Filter `release_id`, pin Delta versions, enforce historical cutoffs, keep
  future truth out of model/policy inputs, and reset each scoring window's
  inventory. See the contracts before implementing.
- Handoffs include PR/commit, entry point/config, input/output schema, meaningful
  checks, limitations and the exact next owner/dependency. A task requiring a
  real run/artifact is not complete with source code alone.
