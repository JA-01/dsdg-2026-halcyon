# Orchestrator guide (for the next orchestrator agent)

You are the **only orchestrator** for team Bay Area Builders in a Kaggle competition. Read this whole file before you act.

## 1. Your job in one paragraph
You coordinate worker agents; you do not do all the work yourself. You keep `main` green and always able to build a valid submission. You assign independent tasks as GitHub issues, one owner each. You decide which merged changes go into the final files, using the evaluation rules below. You build the final files, run Databricks, and tell the **humans** which files to upload. Agents never upload to Kaggle.

## 2. Read first, in this order
1. `AGENTS.md`: team rules and the file-ownership table.
2. `handoff.md`: current state, final files, open next steps.
3. `summary.md`: everything that was done and why.
4. `docs/adr/0001-architecture.md`: contracts and the evaluation protocol.
5. `kaggle_instructions.md`: competition rules and scoring.

## 3. The message board
- **Where:** board = GitHub issue **#75**. The tool is `tools/board` (needs `gh` logged in). The default issue is already 75.
- **Commands:**
  - `tools/board whoami`: confirm your login.
  - `tools/board unread`: new posts since you last checked.
  - `tools/board read -n 10`: the last 10 posts.
  - `tools/board post "[<Human>'s <Agent>] text"`: post. Always start with that prefix.
- Do not maintain perpetual board watchers. Check unread posts at task start, before commits, and after merges; if blocked, switch tasks or record a handoff and sign off.
- **Team logins:** `@AV-01` (AV), `@andrewkwon0804-web` (Andrew), `@tbhojo` (Tejas), `@JA-01` (Jaseer). `AGENTS.md` identifies the current sole orchestrator.
- **Posting rules. Breaking them caused last run's failure:**
  - Never post ACKs, thanks, or "I'm continuing". Silence means working.
  - Post only: a decision, an assignment, a merged result with numbers, a real blocker, or a question.
  - A status line about every 30 minutes at most.
  - Every number must say "local estimate" or "official".

## 4. How to delegate
1. **Find the lever.** Run the scorer (§6) and look at which score part is weakest: P (prediction), F (cost), R (resilience).
2. **Create one issue per task:** `gh issue create --assignee <login> --title "Track X: ..." --body "..."`. The body must contain:
   - **Owner** and the **exact files** they own (new files are fine).
   - **Why**: which score part, and the current numbers.
   - **Change**: concrete steps.
   - **Acceptance**: "merge if the 11-origin mean improves and the worst origin doesn't drop. Report window 208 once."
3. **Tag the owner on the board** with the issue number and a one-line summary.
4. **Keep tasks independent:** never make A wait for B. If B needs something small from A, B may ask A directly on the board.
5. **Two people on the same big lever:** give the second person a **separate file** with the same function contract (a "challenger"). You wire the winner into `submit.MODELS`.
6. **If a worker goes quiet** for about 20 minutes on a long task, post one status ping. If there's no answer in 5 more minutes, tell the human to check that worker's session.
7. **If a worker hits a usage limit or signs off with work left,** reassign it, or do it yourself. Update the `AGENTS.md` ownership table when files change hands.
8. **For read-only research,** you can spawn subagents (task/scout agents) yourself. They found the most valuable signal in this project.

## 5. Ownership (who edits what)
See `AGENTS.md` §4. Only the owner edits a file. If you must edit someone else's file, because they're offline and it's urgent, say so on the board first.

## 6. Evaluating a change. NEVER skip this.
```sh
.venv/bin/python -m pytest -q                       # must be all green before any push
.venv/bin/python -m halcyon.score                   # 11 selection origins: mean and worst
.venv/bin/python -m halcyon.submit --cutoff 208 --out /tmp/h.csv
.venv/bin/python -m halcyon.score --file /tmp/h.csv --start 209 --end 221   # held-out, ONCE
```
- **Choose only on the 11 origins (cutoffs 65..195).** Weeks 209–221 are the held-out test. Look at them once per merged change and never tune on them.
- **Merge rule:** the 11-origin mean goes up (≥ about 0.2 for new complexity) and the worst origin doesn't drop much.
- **Our scorer vs Kaggle:** within about ±1.3 points so far (V1 −1.3, U2 −0.6, ours about +0.6).
- **After any merge that touches the models,** rebuild the final files (§7) and confirm two things: the honest and copied files of each pair have identical private rows, and the primary and hedge have identical public rows.

## 7. Final files and Databricks
```sh
release_dir=$(mktemp -d artifacts/release-XXXXXX)
for spec in "basecase_honest-public:" "KESban-hedge_honest-public:--hedge" \
            "basecase_copied-public:--released-public" "KESban-hedge_copied-public:--hedge --released-public"; do
  n=${spec%%:*}; a=${spec#*:}; .venv/bin/python -m halcyon.submit $a --out "$release_dir/$n.csv"; done
# Only on an authenticated workstation, after accepted source is committed/pushed:
git fetch && .venv/bin/python tools/databricks/bootstrap.py --job-id 838646686083545
```
- **Databricks** builds both models from the committed `origin/main`, so push first.
- **Check the result:** download its CSVs from the Volume path printed in the run's `result.json`. Compare values against the local files: differences ≤ 1e-9 are fine. The sha will differ because of floating-point formatting.
- **Never** create grants or a second job. The job's run-as identity belongs to AV.
- Rebuild into a fresh directory. Never overwrite original uploaded files or treat a different rebuilt hash as proof of parity with the official champion.

## 8. What humans must do. Remind them, don't do it.
- Upload files to Kaggle (5 per day) and tick **"Use for Final Score"** on up to 2, before **Sunday 12:00 CT**.
- Final scoring is confirmed best-of-two, not averaged (`handoff.md`). Humans authorize the uploads and which submissions to select; agents do not make Kaggle selections.
- Upload the ~3-minute video to the team Drive folder by Sunday 12:00 CT. It's 20% of placement.

## 9. Room for improvement (ideas not finished)
1. **Data exploration first.** Spawn exploration subagents in the first hour, not the fifth. The futures-basis signal was found late.
2. **Rhythm gap (74.30 vs our 70.76 public).** Unexplained. Both order-side and forecast-side analyses say it isn't reachable from data ≤ 208 without risky bets.
3. **Warning-confidence challenger (#126): rejected.** The best predeclared weight gained only +0.0355 local mean, entirely at origin 156; do not repeat the same sweep.
4. **First-basis-flag-age challenger (#125): rejected.** Episode-deduplicated age/horizon estimates gained only +0.0122 local mean; the incumbent stays live.
5. **Cleanup:**
   - `databricks/databricks.yml` and `databricks/resources/` describe a bundle job that was deleted.
   - `halcyon/policy_challenger.py` and `halcyon/disruption.py` are no longer on the live path. They're kept as alternatives and tested.

## 10. Hard rules
- Never upload to Kaggle. Never ask workers to.
- Never push with failing tests. Run `pytest` and read the result; don't just pipe it to `tail`.
- Never tune on weeks 209–221.
- Never wait idle on another agent. Assign, then do your own work.
- Before you end the session, post a handoff on the board, tell workers to sign off, and sign off explicitly.
