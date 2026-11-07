# Independent policy challenger (#85)

Local estimates over11 rolling origins65,78,…,195,13 weeks each. Both policies
use the same live duration disruption forecasts and price mean-reversion model.
Data available after each cutoff is hidden; full future demand is published.

| Policy | Mean score | Worst score | Mean F | Mean fill skill | Diversification |
|---|---:|---:|---:|---:|---:|
| Primary LP (f24e2cf) |42.314|2.908|0.7072|0.2324|0.4171|
| Greedy challenger |45.920|26.672|0.6707|0.3215|0.7722|
| Archived U2 policy, fresh forecasts |42.670|22.300|0.4985|0.4064|0.9779|

The challenger reserves cutoff-estimated supplier capacity in weekly slots,
assigning demand to the cheapest feasible arrival slots. Opening stock covers
five times first-week demand. A one-week anticipation buffer moves purchases
forward without adding terminal inventory. Piecewise increasing supplier costs
promote diversification. It uses trailing-four-week median capacity, maximum
lead and mean landed cost. This version is intentionally independent of risk
forecasts; differences in country/route state enter through realized supplier
capacity and lead history. It does not forecast future recoveries or new shocks.

Six development settings were tried: buffer0/diversity0,1/0,1/.1,1/.2,1/.4,2/.2.
Their mean scores were42.68,41.11,45.92,44.41,42.84,43.25, respectively. Selected
1/.1 on mean score.1/.2 had better worst score30.65 but lower mean44.41.
These origins informed selection and are not an untouched holdout. U2's official
59 is a different public window and cannot be compared to these local totals.

Reproduce: `python databricks/challenger_backtest.py --output /tmp/challenger.csv`.
Committed CSV contains all per-origin metrics for both policies. Future supply
mutation leaves decisions unchanged. Tests also check supplier capacity and
eligibility, nonnegative finite orders, opening inventory and final-order taper.
AV owns choosing/wiring the live policy; this PR does not change submit.py.

Against the current primary, the challenger wins5/11 windows and loses6/11;
its worst regression is−20.80 points at182. Against archived U2 policy it wins
8/11 windows. U2 is replayed from origin/archive/phase1-v1 optimize_orders with
cost_tilt=3 and risk_buffer_weeks=4, using the SAME fresh forecasts and scorer.
This isolates policy changes and does not reproduce the original forecast
columns or its official public score. Future supply is hidden from planning.

## Refinement against primary v3 and updated forecasts

At main7078de4, changing recent lead estimates from maximum to ceiling-median
and penalizing early arrivals at4% in the planner (actual scorer holding stays
2%) raises the live50/50 ensemble mean48.220→48.500, worst32.298→32.303.
Standalone challenger mean47.459/worst26.635; primary v3 mean48.766/worst32.459.
The primary is now stronger than the fixed50/50 blend; AV owns blend selection.
All35 tests pass. Fresh per-origin metrics are in
`policy-challenger-refinement-results.csv`; the reproduction script now labels
primary, challenger and live ensemble separately.

Rejected refinements: extra shared-lane cost penalties, optimistic capacity
recovery driven by forecast disruption decay, larger anticipation buffers and
higher supplier-diversification penalties all reduced ensemble mean score.
Latest-capacity haircuts added only0.003 points and were omitted. These settings
were selected on the same11 development windows; no holdout claim is made.

After AV selected primary-only live and challenger as HEDGE_MODELS (main1cb0f12),
the refined standalone challenger is47.459/26.635 mean/worst; current primary
is48.972/34.173. The original challenger with the same new forecasts was46.87/26.67.
Current per-origin CSV now reflects those live/primary/hedge labels. The hedge
build validates260 rows (SHA9c2daaf3b54e05b0e162b4121d3318ee2b48f802e6ac571000c8099653b8257b).
