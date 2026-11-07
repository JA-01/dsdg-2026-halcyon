# Current-main Databricks pipeline

Uses the existing `halcyon` OAuth profile and `workspace.halcyon` project.
The SDK upload, explicit CSV schemas, notebook import and serverless job APIs
come from `origin/archive/phase1-v1`; the notebook calls the fresh package's
`halcyon.submit.build` and `validate` directly.

Run from the repository root with Python dependencies from `pyproject.toml`
plus `tools/databricks/requirements.txt` installed:

```sh
python tools/databricks/bootstrap.py --prepare-only
python tools/databricks/bootstrap.py
```

Run `git fetch origin` first. The bootstrap packages **committed origin/main**, not
working-tree code. Use `--source-ref <commit>` for a specific committed candidate.
`--prepare-only` runs build/validate from that exact source ZIP locally and
checks all ten CSV schemas without network calls. Authentication stays in
the external Databricks profile; no secrets are written to the repo.

The remote command uploads the selected package and local `data/*.csv` into
a unique `/Volumes/workspace/halcyon/raw/phase2/<timestamp>/` directory,
imports `/Workspace/Shared/halcyon/phase2/Submission`, and creates/updates only
the dedicated `halcyon-phase2-submission` job. Existing archived jobs and tables
are left alone. The job overwrites ten dedicated `workspace.halcyon.c2_*`
Delta tables, reads those tables into the current package, validates its
260-row output, and logs parameters, descriptive metrics and CSV to MLflow
experiment `/Shared/halcyon/phase2`. These metrics are not competition scores.

Outputs are unique per MLflow run:
`/Volumes/workspace/halcyon/artifacts/phase2/<mlflow-run-id>/submission.csv`
and `result.json`. The job prints its run URL. Receiving a run ID does not
mean success; inspect the terminal result and task output:

```sh
databricks jobs get-run RUN_ID --profile halcyon --output json
databricks jobs get-run-output TASK_RUN_ID --profile halcyon --output json
```

Get `TASK_RUN_ID` from the parent's `tasks` array. A successful notebook result
reports CSV path, validated row count, source revision and MLflow run ID.
Re-run after each modeling merge, from updated main, to produce the integrated
candidate. This does not upload anything to Kaggle. Humans must complete the
Databricks opt-in form before Sat Nov 7, 18:00 CT.

Local verification on Nov 7: source `b13c027f98bface210c20e90d9e880360f98eb1d`
validated 260 rows and ten input schemas; both Python files compile. The local
`halcyon` Databricks authentication profile reports valid. A live execution was
blocked before remote writes by automatic approval review, which requires
explicit human authorization to upload the repository package and competition
CSVs to `https://dbc-7e1d4af4-7a60.cloud.databricks.com` and deploy/run this job.
No Phase 2 remote success is claimed.
