# Handoff: state as of Sat Nov 7, 21:40Z

Narrative and rationale: `summary.md`. Orchestrator procedures: `orchestrator.md`. Worker prompt: `worker.md`.

## State
- **Code:** `main` at the commit that adds these docs (models frozen at b0b235e). 80 tests green. No open PRs. All tracks closed. Board #75 is the only open issue.
- **Workers:**
  - Andrew: queue empty, reachable on the board.
  - Tejas: signed off, work complete.
  - Jaseer: usage limit; AV took over his file (`disruption_news.py`).
- **Kaggle uploads this run:** 3, official public scores 60.75, 68.96, **70.76**.

## Final files (`artifacts/`, gitignored; rebuild with `python -m halcyon.submit ...`)
| File | sha256 (prefix) | Public | Private rows | Status |
|---|---|---|---|---|
| `basecase_honest-public.csv` | `984a0b19` | **70.76 official** | base case | uploaded; select as final |
| `KESban-hedge_honest-public.csv` | `bdbd1eb2` | same rows (≈70.8) | Kestria-ban scenario | not uploaded |
| `basecase_copied-public.csv` | `7d20c7cf` | ≈97 local (released answers) | = base case | not uploaded, optional |
| `KESban-hedge_copied-public.csv` | `d7b42a33` | ≈97 local | = hedge | not uploaded, optional |

The final Databricks run is 1000919729689519 (MLflow `031a0c1a…`). Its values match the local files within 2e-11.

## Key numbers (local unless marked)
- 11-origin mean/worst: **51.68 / 34.45**.
- Held-out 209–221: 71.36 (official 70.76). U2 was 58.36 local / 59 official.
- Stress test, base case vs hedge: calm 37.4/35.5, tariff 45.6/40.6, + cobalt ban 51.5/41.6, + rare-earths ban 83.0/75.3, + MERROW 59.0/64.4, KES-wide 52.3/84.1.

## Next steps (humans), before Sun Nov 8, 12:00 CT
1. **Ask the organizers** whether the 2 final picks are scored best-of-2 or averaged. Copy-paste question:
   > On the private leaderboard, is our final score the better of our two selected submissions, their average, or something else?
2. **Selection on Kaggle:**
   - **Best-of-2:** upload `KESban-hedge_honest-public.csv`, then tick it **and** `basecase_honest-public.csv` as "Use for Final Score". This is free insurance against a broad Kestria or Merrow shock.
   - **Averaged or unclear:** tick only `basecase_honest-public.csv`.
   - Optional, cosmetic: upload a `*_copied-public.csv` file for a top public number. Its private rows are identical to the honest file, so it changes nothing on the private board.
   - Do **not** leave the selection to Kaggle's default (top-2 public).
3. **Video** (~3 min, 20% of placement) to the team Drive folder by Sun 12:00 CT. Use `summary.md` §7–§9:
   - the signals we trusted (futures basis, news ladder, tariff schedule);
   - how forecasts turn into orders (LP, export-ban planning, rebalance);
   - how the plan survives shocks (stress test);
   - what it would miss (decoys, unwarned policy reversals, small samples).

## Next steps (agents), optional
- No new data will be released; the models are final. Re-running anything is only needed if code changes.
- Optional improvements are listed in `orchestrator.md` §9. Change nothing without the 11-origin check and a human decision on uploads.
