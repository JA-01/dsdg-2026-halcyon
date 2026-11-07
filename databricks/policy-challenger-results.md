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
