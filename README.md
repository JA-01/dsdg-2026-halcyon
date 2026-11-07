# Halcyon — Supply Chain Disruptor

Bay Area Builders' Databricks-track entry for the DSDG Hackathon, November 6–8,
2026. Forecast disruption risk and benchmark prices for 10 materials, then plan
weekly orders and supplier shares to keep demand filled at lower cost.

The finished product is a reproducible Databricks pipeline that exports one
valid 260-row competition CSV, records baseline/candidate evidence in MLflow,
and supports an approximately 3-minute methodology video. Delta tables and Spark
joins work now; forecasting, simulation and full integration are next.

## Agents: start here

Read [AGENTS.md](AGENTS.md), [the implementation plan](docs/implementation-plan.md),
[contracts](docs/contracts.md), and [your handoff](docs/agents/README.md).
Andrew owns the larger integration/release workload; Tejas owns forecasting;
AV owns simulator/policy; Jaseer retains existing environment support and human
review. The plan links assigned issues, boundaries and completion gates.

Product authority: [Databricks requirements](docs/databricks-requirements.md),
[competition rules](kaggle_instructions.md), and
[participant cheat sheet](<Participant Cheat Sheet (share with teams).md>).
The generated root `requirements.md` is excluded.

## Working workspace

- [Databricks workspace](https://dbc-7e1d4af4-7a60.cloud.databricks.com)
- Shared project folder: `/Workspace/Shared/halcyon`
- Schema: `workspace.halcyon`; 10 source and 2 derived Delta tables
- Volumes: `/Volumes/workspace/halcyon/{raw,artifacts}`
- Existing setup job: `408041045566144`; experiment: `/Shared/halcyon/setup`

Each person authenticates using their own account:

```bash
databricks auth login --host https://dbc-7e1d4af4-7a60.cloud.databricks.com --profile halcyon
databricks current-user me --profile halcyon
```

[Setup status and links](docs/databricks-setup-status.md) ·
[Provisioning instructions](tools/databricks/README.md) ·
[LLM/CLI/SDK research](docs/databricks-llm-integration.md)

## Team communication

```bash
tools/board unread
tools/board post "[Your Name's Agent] concrete update; @owner next action"
tools/board read -n 20
```

The [Message Board](https://github.com/JA-01/DSDG-Hackathon/issues/1) coordinates
work. Follow branch/PR/ownership rules in `AGENTS.md`; `CLAUDE.md` imports them.

## Delivery gates

1. Complete baseline pipeline, validated CSV and MLflow artifacts.
2. Fixed-origin backtests comparing forecasts and ordering improvements.
3. Phase 2 rerun through week 221 with fresh private-window inventory.
4. Final CSV selection and video before Sunday, November 8, noon Central.
   Databricks opt-in closes Saturday, November 7, 6 PM Central.

Planning commands/APIs are targets until assigned implementation lands.
Existing commands under `tools/databricks/` work now.

## Run the pipeline

```bash
python3.12 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest -q
.venv/bin/python -m halcyon.pipeline --config configs/phase1_baseline_local.json     # local CSV sources
.venv/bin/python -m halcyon.submission outputs/<run_id>/submission.csv               # validate any export
.venv/bin/python -m halcyon.compare --config configs/compare_dev.json                # backtest candidates
.venv/bin/python -m halcyon.deploy --config configs/phase1_inventory_delta.json --run # real Databricks job
```

Interfaces are in [docs/contracts.md](docs/contracts.md); the Phase 2 steps are in
[docs/phase2-runbook.md](docs/phase2-runbook.md).
