# Simulator and policy handoff (#8)

Implemented by AV. Local economics are **proxy**, not organizer simulator parity
or an official competition score. Forecasting, Delta/MLflow packaging, final
candidate selection and external submission remain their assigned owners' work.

## Integration API

```python
from halcyon.policy import InventoryPolicy, NaivePolicy, PolicyConfig
from halcyon.simulator import SimulatorConfig, simulate_window

view = data.as_of(cutoff)
# Call separately for EACH independent public/private window.
decisions = InventoryPolicy(config=PolicyConfig()).decide(
    view, window_forecasts, cutoff, target_weeks
)
result = simulate_window(
    decisions, data["demand"], data["supply_history"], data["suppliers"],
    data["outcomes"], target_weeks[0], target_weeks[-1],
    config=SimulatorConfig(), reference_costs=None,
)
```

`Dataset` uses mapping-only access. Both policies implement the shared `decide`
protocol. `Policy` names `InventoryPolicy`; `NaivePolicy` is the explicit baseline.
The pure inventory helper is:

```python
plan_orders(forecasts, demand, supply_history, suppliers, cutoff,
            target_weeks, *, config=None)
```

Forecast columns: `target_week, material, disruption_prob, price_forecast`.
Decision columns: `target_week, material, order_units` plus all six canonical
`share_*` columns. Raw table schemas are unchanged. Target weeks must be a
consecutive increasing window strictly after cutoff; a private-window gap is
allowed. Forecasts must cover exactly the supplied window/materials. Shares
remain eligible and sum to one even when orders are zero. No repair on export.

The policy internally filters realized supply to `week <= cutoff`, even if its
caller accidentally supplies a full frame. The evaluator, conversely, requires
realized supply for the target window and outcomes from
`max(1, start_week - 4)` through its end. Missing lookback rows are errors: a shock
before the window still contributes its four-week recovery tail. Never use the
evaluator's future frames or cost references as policy inputs.

## Economics and unresolved organizer rules

Each simulator call starts fresh, with no transit and no state retained.

| Rule | Default | Alternative / limit |
| --- | --- | --- |
| Initial stock | Five times first target week's demand; free opening inventory | `initial_stock_mode="five_week_sum"` sums the first five known demand weeks, including beyond a shorter evaluation window |
| Reference unit cost | Unweighted realized supplier-week mean landed cost within this window | `reference_costs` mapping/Series supplies exactly one positive finite value per material; historical means tested separately |
| Supplier fill | `min(order * share, realized capacity)` independently | Unfilled slices cancelled, unpaid, never reallocated |
| Arrival | Order at t arrives t + realized integer lead | Zero lead supported; all current arrivals precede consumption |
| Demand | Consume available stock, lose unmet demand | No backlog |
| Holding | 2% reference cost on stock remaining after demand; no transit holding | `holding_timing="pre_demand"` charges after-arrival stock before consumption |
| Shortage | Unmet units × 5 × reference cost | `shortage_multiple` configurable |
| Terminal salvage | 70% reference cost × ending stock plus all transit | Includes arrivals beyond window; `salvage_rate` configurable |
| Quantity | Fractional supplier slices | `quantity_rounding="floor"` floors each requested slice before capacity; discarded fractions included in cancellations |
| Diversification | `(1 - sum(shares**2)) / (1 - 1/n_eligible)` | Unweighted mean across material/weeks, including zero-order rows; one supplier gives zero |
| Fill aggregation | Total fulfilled / total demand | Shock fill uses only shock/recovery rows; zero denominator gives NaN |

`holding_rate`, `shortage_multiple`, `salvage_rate` are explicit config fields.
Costs can be negative because opening stock is free and terminal salvage earns
credit. Default zero landed-cost references are permitted for zero-cost fixtures;
explicit reference overrides must be positive. Shares within the shared `1e-6`
tolerance are used unchanged, not normalized, so tiny quantity differences remain.

No hindsight plan or exact official financial/fill-skill normalizer is known.
No F/P/R/total-score estimate is emitted. Undefined fill denominators stay NaN,
not perfect scores. The [organizer Code page](https://www.kaggle.com/competitions/dsdg-hackathon-2026-supply-chain-disruptor/code)
was inspected with both reader and Chromium: the unauthenticated page showed
“Invitation required” and one participant notebook, not an identifiable organizer
simulator. No external code was imported. Organizer clarification was requested
on the team board for reference costs, initialization, timing, rounding and
hindsight/aggregation. These assumptions remain explicit until authoritative
source is supplied.

## Ordering policies

`NaivePolicy` (`local_origin_naive`) orders that week's known demand entirely
from the static largest-normal-capacity eligible supplier. Equal-capacity ties
use canonical country order. Its orders and shares match all 260 checked-in
organizer sample rows exactly; this does **not** establish forecast, financial
normalizer, or simulator parity. It never reuses week-208 sample values at an
earlier historical origin.

`InventoryPolicy` (`inventory_cover`) uses a finite-horizon, deterministic
inventory-cover heuristic, not a calibrated stochastic optimizer:

- Trailing calendar-window means estimate capacity, landed cost and lead.
  Capacity is capped by static normal capacity; lead is rounded upward.
  Every eligible supplier needs recent history, otherwise raise an explicit error.
- Opening stock is five times this call's first-week demand; projected arrivals
  and lost demand are tracked only from cutoff-safe estimates.
- Cover is maximum estimated lead + one review week + safety cover + current
  forecast risk × risk buffer + positive near-future forecast price growth ×
  price cover (growth capped at one).
- Smooth cost/lead preferences blend with the best supplier; a shared-lane
  penalty discounts correlated routes. Filled planned slices respect predicted
  capacities. Remaining useful demand is recomputed after each allocation so
  unequal leads and existing pipeline are not counted twice.
- Do not buy units expected to arrive after the window or solely for salvage.
  Zero-order rows retain normalized eligible preference shares.

`PolicyConfig` defaults: `trailing_weeks=8`, `safety_cover_weeks=1`,
`risk_buffer_weeks=2`, `price_cover_weeks=2`, `cost_weight=1`, `lead_weight=0.2`,
`diversification_weight=0.75`, `lane_weight=1`. These are explicit initial
heuristic settings, not holdout-tuned claims. A new shock can still cancel a
slice or delay arrival; the submitted policy cannot react to future realized
state. Material-level disruption probabilities do not identify the affected
supplier. This is a remaining model/policy limitation.

## Result schema

`SimulationResult.metrics`: one aggregate row (`material="__all__"`).
`material_metrics`: one row per material. Both include `window_id`, unit/cost
sums, `fill_rate`, shock demand/fulfilled units and `shock_fill_rate`,
`mean_concentration`, and `mean_diversification`.

`weekly` is keyed by `window_id, week, material` and contains:
`demand_units, fulfilled_units, stockout_units, ending_stock, ending_transit,
ordered_units, filled_order_units, cancelled_units, purchase_cost, holding_cost,
shortage_cost, salvage_credit, total_cost, shock_recovery, concentration,
diversification`. Total cost = purchase + holding + shortage - salvage.
`assumptions` is JSON-serializable and records configuration, realized reference
costs and opening units. `score_status` is always `"proxy"`.

Andrew should attach run/release/cutoff/window IDs when persisting these frames;
the helper does not mutate global Spark state or own MLflow runs.

## Exercised evidence

Runtime: Python 3.14, pandas 3.1.1, numpy 2.5.4, pytest 9.2.0. Command:

```sh
.venv/bin/python -m pytest -q
```

155 tests passed, including hand-calculated fill/cancel/arrival/cost/salvage,
independent resets, prior-window recovery, fractional/nonfinite week rejection,
origin mutation invariance, lane diversification, demand/risk/price responses,
terminal inventory bounds, and assumption alternatives. No official score test.

A real-data smoke run called `notebooks.policy.evaluate.evaluate_policies` using
a disposable forecaster fixture: historical per-material disruption rates and
last-known benchmark prices at each cutoff. It did not use Tejas's candidate
model or tune/evaluate the reserved origin 182. Both subwindows use the same
forecast origin, each with fresh inventory. The callable accepts the pipeline's
real `Dataset` and `Forecaster`; Andrew can replace the fixture without changing
policy/evaluation code.

Default proxy results (costs in Aurelian dollars; fill percentages):

| Origin | Window | Policy | Total cost | Overall fill % | Shock/recovery fill % |
| --- | --- | --- | ---: | ---: | ---: |
| 130 | 131–143 | Local naive | 6,901,576.23 | 91.6101 | 84.1792 |
| 130 | 131–143 | Inventory cover | 5,295,252.72 | 99.1658 | 98.9507 |
| 130 | 144–156 | Local naive | 4,405,133.65 | 100.0000 | 100.0000 |
| 130 | 144–156 | Inventory cover | 4,280,581.87 | 99.9478 | 100.0000 |
| 156 | 157–169 | Local naive | 4,528,032.35 | 100.0000 | 100.0000 |
| 156 | 157–169 | Inventory cover | 4,571,698.51 | 99.2380 | 99.9309 |
| 156 | 170–182 | Local naive | 8,362,017.89 | 86.5403 | 80.8211 |
| 156 | 170–182 | Inventory cover | 5,580,715.23 | 94.6028 | 92.3095 |

Inventory cover reduces default cost in three windows and regresses 0.96% in
157–169. Calm-window fill can regress; this is not uniformly superior. Five-week
summed opening stock increases the worst cost regression to 3.96%; floor rounding
to 1.81%; pre-demand holding to 0.91%. Historical reference costs improve all
four cost comparisons, illustrating that the missing organizer cost definition
matters. Diversification is approximately 0.93–0.94 versus naive zero.

The exercised notebook writes 40 comparison rows (two origins × two windows ×
two policies × five scenarios), decision/weekly/material CSVs and a manifest
with per-window assumptions and source hashes. Local ignored evidence is under
`artifacts/policy-evaluation/`; it must be copied into the real run by Andrew,
not described as already logged in Databricks/MLflow.

A cutoff-208 two-window smoke also produced and reread a valid 260-row export:
`artifacts/policy-evaluation/policy-smoke-submission.csv`, SHA-256
`734c30db0566c6968a43bc527958d264533fb22adf248f29f3d22bf825641247`.
That CSV uses the disposable baseline forecast fixture, not the final forecast
candidate and not an external submission. The temporary smoke script was not
retained as product code. Final holdout and actual end-to-end Databricks evidence
belong to the integrated comparison/release stage.
