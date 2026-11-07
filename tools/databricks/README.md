# Databricks workspace setup

The bootstrap provisions `workspace.halcyon`, managed `raw` and `artifacts`
Volumes, a shared setup notebook, and a saved serverless job. Its notebook
loads all 10 competition CSVs into Delta tables, checks schemas/keys/checksums,
builds supplier/material Spark aggregates, validates the organizer's baseline
CSV, and logs an MLflow setup run. This is infrastructure and data preparation,
not a trained forecast or an official Kaggle submission.

## Local environment

```bash
brew install databricks/tap/databricks python@3.12
python3.12 -m venv "$HOME/.venvs/dsdg-hackathon"
source "$HOME/.venvs/dsdg-hackathon/bin/activate"
python -m pip install -r tools/databricks/requirements.txt
databricks auth login --host 'https://YOUR-WORKSPACE-HOST' --profile halcyon
```

Keep OAuth profiles and credentials outside Git. The CLI and SDK share the
`halcyon` authentication profile. No additional API key or MCP server is needed
for launching jobs and inspecting data through the SDK/SQL API.

## Provision and run

Run from the repository root:

```bash
python tools/databricks/bootstrap.py --prepare-only
python tools/databricks/bootstrap.py
```

The first command validates local source shapes/keys without authentication or
remote mutations. The second provisions resources, uploads sources, and starts
the job. It prints the run URL and saves non-secret IDs in
`~/.local/share/dsdg-databricks/workspace.json`.

The default catalog is `workspace`; use `--catalog` and `--schema` to select
another authorized location. The release ID includes observed outcome coverage
and a content fingerprint, so the Phase 2 files produce a new release path.

The saved job runs only on request, allows one concurrent run, and has a
30-minute timeout. It uses a pinned Python environment on serverless compute.
The notebook also declares its dependencies for interactive use. Subsequent
bootstrap invocations update only the job tagged `managed_by=dsdg-bootstrap`
and replace only the matching release snapshot in each Delta table. Other
releases and existing resource ACLs are preserved. Coordinate notebook/job
edits before rerunning bootstrap because it redeploys its setup notebook and
job settings.

Inspect execution using the printed IDs:

```bash
databricks jobs get-run RUN_ID --profile halcyon --output json
databricks jobs get-run-output TASK_RUN_ID --profile halcyon --output json
```

`TASK_RUN_ID` comes from the parent run's `tasks` array. Success means a terminal
`SUCCESS` result, not merely receiving a run ID. The notebook exits with a JSON
report, and stores the same report and baseline CSV in the artifacts Volume.

## Team access

First add each person in the dashboard: **Settings → Identity and access →
Users → Manage → Add user → Add new**. They must use their own sign-in email.
Then grant project permissions:

```bash
python tools/databricks/share.py friend@example.com another@example.com \
  --warehouse-id WAREHOUSE_ID --experiment-id EXPERIMENT_ID
```

This adds, rather than replaces, permissions: folder editing, job-run
management, catalog usage, and table/Volume/model work within the project
schema. Warehouse usage and MLflow experiment editing are granted when their
IDs are supplied. The script requires existing active workspace users and
checks permission responses after granting access. It does not invite users
or assign workspace administrator roles. No teammate emails are hardcoded.

The integration lead can additionally receive setup-job editing permission:

```bash
python tools/databricks/share.py integrator@example.com \
  --manage-job-email integrator@example.com
```

The manager must also be listed as a project member. Existing job owner/manager
rights are preserved on ordinary reruns, so sharing again cannot downgrade the
integrator. Andrew has this scoped permission for Phase 2 redeployment. It does
not assign a workspace administrator role. The separate training job/experiment
remain Andrew's next implementation task.

All teammates use **Workspace → Shared → halcyon** for the notebook and
**Catalog → workspace → halcyon** for tables and files. MLflow is in
`/Shared/halcyon/setup`. Each friend's coding assistant can authenticate to the
same workspace using its own local `halcyon` profile.

## Output contracts

- `bronze_<csv-name>`: source columns plus `release_id`, `source_sha256`, and
  `ingested_at`. Natural keys are unique within each release.
- `silver_supplier_week`: price, supplier, tariff, shipping, and macro joins
  at `(release_id, week, material, country)` grain.
- `silver_material_week`: observed average spot price, supplier count, and
  mean congestion at `(release_id, week, material)` grain. These are historical
  observations, not automatically safe future prediction features.
- `artifacts/<release_id>/setup_report.json`: validated counts, Delta versions,
  and MLflow identifiers.
- `artifacts/<release_id>/baseline_sample_submission.csv`: an unchanged copy
  of the valid organizer baseline, explicitly not a trained candidate.

The forecast pipeline must still enforce cutoff/horizon availability, train
models, backtest ordering policies, and log baseline/candidate comparisons as
described in [the requirements](../../docs/databricks-requirements.md).
