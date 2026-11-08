# Team rules for every agent

## 1. The board (pinned GitHub issue)

Every agent reads and posts on the pinned "Message Board" issue via `tools/board` (needs only `gh`, logged in). Set `BOARD_ISSUE` if it is not issue #1.

- Start every post with `[<human>'s <agent>]`, e.g. `[Sam's Codex]`. Keep it short: what changed, which files or contracts, what you need, from whom.
- Mention by GitHub login. Fill in your team: `@login1` (Name), `@login2` (Name), `@login3` (Name), `@login4` (Name), `@all` (everyone).
- **Mentions you or `@all`:** act on it and reply promptly.
- **Not addressed to you:** still read it. Reassess your own work only if it is affected (a contract, a file you own, something already done). Do not redo finished work, and do not reply just to acknowledge.
- Before editing another teammate's files, ask for a handoff on the board and wait for the owner or the team lead.

Polling is incremental (about one cheap API call per poll, 30 s default) so a shared token stays under GitHub's rate limit. Commands: `tools/board unread` (new posts, marks read; flags MENTION), `tools/board read -n 20`, `tools/board post "[Name's Agent] text"` (or pipe stdin), `tools/board wait` (blocks until someone else posts), `tools/board whoami`.

**Stay in the loop:**
- Run `tools/board unread` at task start, before each commit, and after merges.
- Do not maintain perpetual board watchers. If blocked, record the dependency, switch to independent work, or sign off.

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

Campaign #128–131 was **cancelled by human direction; all workers and the orchestrator are SIGNED OFF**. Tejas's Codex (@tbhojo) was the last orchestrator, not an automatically active owner of a new run. Read `handoff.md` before acting. A new human directive must designate the orchestrator and assign work; no watchers or old assignments should resume automatically. Architecture/contracts: `docs/adr/0001-architecture.md`. Team: `@AV-01` (AV), `@andrewkwon0804-web` (Andrew), `@tbhojo` (Tejas), `@JA-01` (Jaseer). Board: issue #75. File ownership below is retained for handoffs, not active task assignments.

| Area | Owner (GitHub login) | Folders |
|---|---|---|
| Scorer, ordering policy, scenario-policy challenger | andrewkwon0804-web | `halcyon/score.py`, `halcyon/policy.py`, `halcyon/policy_scenarios.py`, their tests |
| Disruption probability (backup model), events, shock hedge, price | tbhojo | `halcyon/disruption.py`, `halcyon/events.py`, `halcyon/news.py`, `halcyon/price.py`, their tests |
| Live disruption model, scope challenger, policy challenger, Databricks track | JA-01 | `halcyon/disruption_news.py`, `halcyon/disruption_scope.py`, `halcyon/policy_challenger.py`, their tests, `databricks/`, `tools/databricks/` |
| FX sanctions challenger (unwired; defects unresolved) | AV-01 | `halcyon/disruption_fx.py`, `tests/test_disruption_fx.py` |
| Integration, contracts, data, final candidates, handoff | tbhojo | `halcyon/data.py`, `halcyon/naive.py`, `halcyon/submit.py`, `tests/test_submit.py`, `docs/adr/`, `data/`, `handoff.md`, `summary.md` |
