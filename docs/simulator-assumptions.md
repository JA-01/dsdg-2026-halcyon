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

## Finite-horizon allocation optimizer (#23)

`halcyon.policy.OptimizedPolicy` is a separate candidate, not a replacement for
the unchanged `InventoryPolicy` or its `Policy` alias. It implements the same
`decide` interface and exposes `policy_id="inventory_milp"`. Use:

```json
{"class": "halcyon.policy:OptimizedPolicy", "kwargs": {}}
```

`OptimizationConfig` accepts a dataclass or a JSON mapping through the constructor:

```python
OptimizedPolicy(config={"base_buffer_weeks": 2.0, "risk_buffer_weeks": 2.0})
```

The pure helper is `optimize_orders(forecasts, demand, supply_history, suppliers,
cutoff, target_weeks, *, config=None)`. It retains the existing point-in-time
validation and independent-window initialization. All configuration values and
input frames are explicit; no implicit network, Spark or model training.

### Estimates and objective

The optimizer uses the trailing 13 calendar weeks through the cutoff. Per
supplier it estimates capacity with the 25th percentile, capped at static normal
capacity, lead with the ceiling of its 75th percentile, and cost with the mean
landed cost. Every eligible supplier needs recent history. All estimates exclude
future realized supply. Forecast price changes scale supplier purchase costs by
`price_forecast[t] / price_forecast[first_target]`; this is a relative curve,
not a claim to forecast each country's absolute landed cost.

The SciPy/HiGHS mixed-integer model selects continuous supplier order slices,
end-stock, unmet demand and preference slacks. It minimizes estimated purchase,
holding and shortage costs, plus soft inventory-buffer and sourcing penalties.
The policy reference cost is the mean of recent supplier mean landed costs,
never the evaluator's future realized reference.

Stock balances obey arrival lead times and known weekly demand. A binary per
week forbids simultaneous positive ending stock and unmet demand. A plain LP
would allow the optimizer to refuse current demand while preserving a safety
buffer, which the actual simulator cannot do. Orders arriving beyond the horizon
are prohibited; terminal stock is fixed to unavoidable excess opening inventory,
so the optimizer cannot manufacture profit by buying solely for salvage.
Salvage is therefore a constant terminal credit under this conservative
restriction, not an incentive to speculate.

The end-stock buffer target is the smaller of remaining known demand and
`(base_buffer_weeks + risk_buffer_weeks * disruption_prob[t])` times mean demand
over the next one or two weeks. Slack makes scarce-supply cases feasible.
Lane-balanced supplier weights are proportional to the inverse count of
eligible suppliers on the same lane. An L1 penalty on deviations from these
weights trades purchase cost against route diversification; it is **not** an
exact HHI or official resilience objective. Zero-order shares are uniform across
eligible countries, maximizing country diversification without buying units;
positive-order allocations retain the lane-balanced preference.

Defaults: `trailing_weeks=13`, `capacity_quantile=0.25`, `lead_quantile=0.75`,
`base_buffer_weeks=2`, `risk_buffer_weeks=2`, `buffer_penalty=0.5`,
`diversification_penalty=0.2`, `holding_rate=0.02`, `shortage_multiple=5`,
`salvage_rate=0.7`. Buffer penalty must be below the positive shortage multiple.
Solver time limit is 60 seconds per material. Failed/nonfinite/infeasible
solutions raise `RuntimeError`; there is no hidden fallback. Only negative
numerical dust within `1e-7` is removed, then balances, bounds, inequalities,
integrality and mandatory consumption are checked against that tolerance.

`decisions.attrs["projection"]` is a JSON-safe list keyed by week/material with
`projected_stock` and `projected_shortage`. These are estimated, not realized
states. The evaluator notebook saves this separately as `*-projection.csv`;
decision columns and exporter compatibility are unchanged.

### Development selection and exercised evidence

Compared two buffer settings on development origins 130/156 only. The initial
low-buffer setting (0.5 base + 1.5 × risk) improved three cost windows but regressed
19.46% in 170–182, with worse shock fill. Rejected it as the default. Selected
the conservative 2 + 2 × risk setting on development data; no origin-182 holdout
forecast or evaluation was performed.

The selected optimizer versus unchanged inventory cover, under default proxy
economics:

| Origin | Window | Optimizer cost | Cost change vs inventory cover % | Overall fill % | Shock/recovery fill % |
| --- | --- | ---: | ---: | ---: | ---: |
| 130 | 131–143 | 5,111,355.63 | -3.4729 | 99.4757 | 99.9605 |
| 130 | 144–156 | 4,332,418.37 | +1.2110 | 99.9693 | 100.0000 |
| 156 | 157–169 | 4,460,014.91 | -2.4429 | 99.9562 | 99.9911 |
| 156 | 170–182 | 5,218,876.32 | -6.4837 | 96.7737 | 95.4028 |

Default overall fill improves in all four windows; shock fill improves in three
and ties in one. Diversification is approximately 0.972–0.975. Raw summed cost
falls 3.07%, but that aggregation is **not** official score aggregation. One calm
window costs 1.21% more. Worst cost regression across the four alternative
evaluator assumptions is 1.29%; this is not a guarantee on unseen shocks.

292 repository tests passed after the forecasting integration; one native Spark
test skipped locally because PySpark is absent from this environment. Added
hand-calculated economic optima, temporal-price/holding tradeoffs, capacity and
lead quantiles, impossible supply, mandatory consumption, fresh window resets,
future-supply mutation invariance, lane preference, request/config errors and
locked-holdout boundary coverage.

The actual real-CSV smoke used Tejas's `HistoricalForecaster`, not a duplicated
fixture, through `evaluate_policies` and the real `run_pipeline`:

```python
from halcyon.data import Dataset
from halcyon.forecasting.baseline import HistoricalForecaster
from halcyon.pipeline import run_pipeline
from halcyon.policy import InventoryPolicy, NaivePolicy, OptimizedPolicy
from notebooks.policy.evaluate import evaluate_policies

data = Dataset.from_csv_dir("data")
evaluate_policies(data, HistoricalForecaster(), "outputs/policy-optimization",
                  policies={"naive": NaivePolicy(), "cover": InventoryPolicy(),
                            "optimized": OptimizedPolicy()})
result = run_pipeline(208, HistoricalForecaster(), OptimizedPolicy(),
                      data=data, output_dir="outputs/policy-optimization/phase1")
```

Notebook defaults still compare the original two policies. Additional policies
use the optional mapping; requesting origin 182 now requires explicit
`allow_holdout=True` for final selection. Manifests include per-policy configs,
per-window evaluator assumptions, source checksums, numerical package versions
and exact policy/simulator/notebook source hashes.

Final local evidence: `outputs/policy-optimization-final/` contains 80 comparison
rows (two origins × two windows × four policies including rejected low-buffer
settings × five evaluator scenarios), real decisions, projected/realized weekly
states and material metrics. The split-window Phase 1 export is
`phase1/local-0dc7a3d10e9a/submission.csv`, 260 valid rows, SHA-256
`219ca02c36eca45a59ecd9ca0e0d9e58b6b87b9dff0bb16cfa5205c8aaab3821`.
Its source manifest records clean implementation commit
`8bd7a60ffec35a209e5ba86414a0ca4783ad675d` (`dirty=false`); the comparison
manifest additionally fingerprints exact exercised source bytes.
These are local artifacts, not a claim of a new Databricks/MLflow run or Kaggle
submission. Andrew owns remote candidate comparison and final selection. New
forecast candidates can change the price/risk inputs and must be compared again
without retuning on the reserved holdout.

### V2 zero-order diversification (#41)

Peer-approved bounded change: exactly-zero optimizer orders use equal eligible
country shares rather than the lane-balanced active-order preference. Solver
objective, quantities, positive-order sourcing and projected state are unchanged.
This minimizes country HHI on rows that ship no units; official score benefit
remains unknown if the organizer excludes or quantity-weights zero-order rows.

Real-data replay covered development origins130/156, both independent windows
and all five existing evaluator scenarios. Quantities and positive-order shares
match the saved pre-change decisions; inventory, procurement, holding, shortage,
salvage and fulfilled/cancelled units match within numerical serialization
tolerance. Default diversification increases0.005769 per development window.
No origin182 evaluation or tuning was performed.

Actual cutoff208 pipeline export passed serialized260-row validation,130 rows
per fresh window. Local smoke SHA-256:
`bcbded2371459959a6e591fe342974a594c18292bab3aa341d0312a573f2ae2f`.
Its forecasts, quantities and positive-order shares match the previous local
smoke;116 zero-order rows now have equal eligible shares. This is not a new
remote candidate or an externally scored submission. The human-reported54.10
incumbent is unchanged and remains archived. Full V2 review and acceptance gates:
[AV's improvement document](agents/av-v2-improvements.md).

