"""Policy-only development comparisons using a caller-supplied Dataset/forecaster.

From the repository root, import evaluate_policies in a notebook and pass the
same Dataset and forecaster used by the pipeline. Default origins are development
folds only. Forecasts are frozen before both independent 13-week policy calls.
No Spark session, network, model fitting, or official competition score here.
"""

from dataclasses import asdict, is_dataclass
import hashlib
from importlib.metadata import version
import json
from pathlib import Path

import pandas as pd

from halcyon.constants import DEVELOPMENT_ORIGINS, FINAL_HOLDOUT_ORIGIN
from halcyon.contracts import historical_windows
from halcyon.policy import InventoryPolicy, NaivePolicy
from halcyon.simulator import SimulatorConfig, simulate_window


def evaluate_policies(data, forecaster, output_dir, *, origins=DEVELOPMENT_ORIGINS,
                      policies=None, allow_holdout=False):
    """Write decisions, weekly states, material metrics and proxy comparisons.

    The caller owns release/version selection and forecaster configuration.
    Full evaluator truth stays separate from each cutoff-filtered policy input.
    Returns a comparison DataFrame; this does not select a final candidate.
    Supply a mapping of policy names to instances to compare additional policies;
    omission keeps the original naive/inventory-cover comparison.
    """
    origins = tuple(origins)
    if FINAL_HOLDOUT_ORIGIN in origins and not allow_holdout:
        raise ValueError(f"origin {FINAL_HOLDOUT_ORIGIN} is locked; allow_holdout is final-selection only")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    suppliers = data["suppliers"]
    demand = data["demand"]
    history = data["supply_history"]
    outcomes = data["outcomes"]
    if policies is None:
        policies = {"local_origin_naive": NaivePolicy(), "inventory_cover": InventoryPolicy()}
    comparisons = []
    assumptions = {}
    for cutoff in origins:
        windows = historical_windows(cutoff)
        target_weeks = [week for window in windows for week in window.target_weeks]
        observed = data.as_of(cutoff)
        forecasts = forecaster.predict(observed, cutoff, target_weeks)
        forecasts.to_csv(output_dir / f"origin-{cutoff}-forecasts.csv", index=False)
        for window in windows:
            weeks = list(window.target_weeks)
            start, end = weeks[0], weeks[-1]
            frozen = forecasts[forecasts.target_week.isin(weeks)].copy()
            prefix = f"origin-{cutoff}-window-{start}-{end}"
            decisions_by_policy = {}
            for policy_id, policy in policies.items():
                decisions = policy.decide(observed, frozen.copy(), cutoff, weeks)
                decisions_by_policy[policy_id] = decisions
                decisions.to_csv(output_dir / f"{prefix}-{policy_id}-decisions.csv", index=False)
                if "projection" in decisions.attrs:
                    pd.DataFrame(decisions.attrs["projection"]).to_csv(
                        output_dir / f"{prefix}-{policy_id}-projection.csv", index=False
                    )
                result = simulate_window(decisions, demand, history, suppliers, outcomes, start, end)
                result.weekly.to_csv(output_dir / f"{prefix}-{policy_id}-weekly.csv", index=False)
                result.material_metrics.to_csv(
                    output_dir / f"{prefix}-{policy_id}-materials.csv", index=False
                )
                assumptions[f"{prefix}:default"] = result.assumptions
                row = result.metrics.iloc[0].to_dict()
                row.update(cutoff=cutoff, window_start=start, window_end=end,
                           policy_id=policy_id, scenario="default", score_status=result.score_status)
                comparisons.append(row)
            # Rerun BOTH policies under each assumption; do not compare unlike economics.
            references = history[history.week <= cutoff].groupby("material").landed_cost.mean()
            for scenario, config, costs in (
                ("five_week_initial", SimulatorConfig(initial_stock_mode="five_week_sum"), None),
                ("floor_quantities", SimulatorConfig(quantity_rounding="floor"), None),
                ("pre_demand_holding", SimulatorConfig(holding_timing="pre_demand"), None),
                ("historical_reference", SimulatorConfig(), references),
            ):
                for policy_id, decisions in decisions_by_policy.items():
                    result = simulate_window(
                        decisions, demand, history, suppliers, outcomes, start, end,
                        config=config, reference_costs=costs,
                    )
                    assumptions[f"{prefix}:{scenario}"] = result.assumptions
                    row = result.metrics.iloc[0].to_dict()
                    row.update(cutoff=cutoff, window_start=start, window_end=end,
                               policy_id=policy_id, scenario=scenario, score_status=result.score_status)
                    comparisons.append(row)
    comparison = pd.DataFrame(comparisons)
    comparison.to_csv(output_dir / "comparisons.csv", index=False)
    manifest = {
        "purpose": "policy-only development comparison; not official scoring or model selection",
        "origins": list(origins),
        "inventory_reset": "independent per 13-week window; both forecast from fold cutoff",
        "assumptions": assumptions,
        "simulator_default_config": asdict(SimulatorConfig()),
        "policy_configs": {
            name: asdict(policy.config) if is_dataclass(getattr(policy, "config", None)) else {}
            for name, policy in policies.items()
        },
        "source_sha256": data.source_sha256,
        "forecaster_class": f"{type(forecaster).__module__}.{type(forecaster).__qualname__}",
        "package_versions": {name: version(name) for name in ("pandas", "numpy", "scipy")},
        "code_sha256": {
            str(path.relative_to(Path(__file__).resolve().parents[2])): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (Path(__file__).resolve(),
                         Path(__file__).resolve().parents[2] / "halcyon/policy.py",
                         Path(__file__).resolve().parents[2] / "halcyon/simulator.py")
        },
        "limits": ["No organizer simulator parity or hindsight denominator",
                   "Release/version and forecast provenance must be attached by the caller",
                   "Sensitivity changes evaluator assumptions, not submitted policy decisions"],
    }
    (output_dir / "policy-evaluation.json").write_text(
        json.dumps(manifest, indent=2, allow_nan=False) + "\n"
    )
    return comparison
