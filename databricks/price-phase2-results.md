# Phase 2 price refinement (#78)

Selected only on the agreed origins 65,78,…,195. Local estimates, not official
competition scores. Preserve the 104-week mean / 26-week half-life and reverse
25% of the latest one-week relative price change, ramping with a four-week
half-life. Clip the return to [-1,1] so extreme quotes cannot make a forecast
nonpositive. A single observation has zero reversal.

| Model | Mean MAPE | Mean raw price skill | Worst raw skill |
|---|---:|---:|---:|
| Last quote | .052955 | .000000 | .000000 |
| Previous slow reversion | .050150 | .052568 | -.051559 |
| Selected partial reversal | .049783 | .058878 | -.074588 |
| Archived U2 recipe | .051999 | .016024 | -.143371 |

Selected model wins 5/11 against previous slow reversion; it regresses at
65,91,104,117,143,156. Worst MAPE increase .001499 at91. The clipped price
component rises .126919 points on average. Under unchanged primary policy and
disruption forecasts (main9401a47), total mean48.612006→48.738925 and
worst33.183035→33.253669. Orders do not consume price forecasts in this policy.

Robustness diagnostic, offset historical origins71,84,…,188: mean raw price
skill .074801→.086285; worst -.054729→-.052511. These windows overlap selection
data and do not constitute independent validation.

Rejected: shorter reversion; 26/52/208-week centers; median, exponentially
weighted, clean-state and same-state centers; 2/4/8-week quote averaging;
positive trend extrapolation; 4/13-week reversal; disruption premium decay.
The experiment searched 80 center/reversion combinations and25 additional
variants, so small gains can reflect selection noise.

Held-out origin208, evaluated once after selection: MAPE .058027→.059610;
raw price skill -.005410→-.032833 (worse). Both clip to zero, leaving total
61.317910 unchanged. No tuning used weeks209–221. Final forecasts use released
history through221. Both primary and shock builds pass260-row validation;
40 tests pass, including future mutation, short history and extreme quote cases.

Reproduce selection:
`.venv/bin/python databricks/price_backtest.py --output /tmp/prices.csv`.
For the diagnostic only, append `--include-holdout`. The committed CSV includes
all four candidates at11 selection origins and the single208 diagnostic.
Databricks final reruns remain AV-owned; no Kaggle uploads were performed.
