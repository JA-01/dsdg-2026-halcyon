# Databricks setup status

Verified November 6, 2026. This documents the working workspace/data setup;
forecast models, policy optimization, and Kaggle submissions are separate work.

## Open the project

- [Workspace](https://dbc-7e1d4af4-7a60.cloud.databricks.com)
- [Shared setup notebook](https://dbc-7e1d4af4-7a60.cloud.databricks.com/?o=7474644438221407#notebook/2557523615426702)
- [Saved serverless setup job](https://dbc-7e1d4af4-7a60.cloud.databricks.com/jobs/408041045566144)
- [Successful setup run](https://dbc-7e1d4af4-7a60.cloud.databricks.com/?o=7474644438221407#job/408041045566144/run/924260566709944)
- [MLflow experiment](https://dbc-7e1d4af4-7a60.cloud.databricks.com/?o=7474644438221407#mlflow/experiments/2557523615426703)

In the dashboard, use **Workspace → Shared → halcyon** for the notebook and
**Catalog → workspace → halcyon** for tables and Volumes. MLflow experiment
path: `/Shared/halcyon/setup`.

## Provisioned resources

| Resource | Identifier |
| --- | --- |
| Project schema | `workspace.halcyon` |
| Raw snapshots Volume | `/Volumes/workspace/halcyon/raw` |
| Output artifacts Volume | `/Volumes/workspace/halcyon/artifacts` |
| Current release | `weeks-1-208-18caf03f890c` |
| Notebook | `/Workspace/Shared/halcyon/Workspace Setup` |
| Job | `408041045566144` |
| Successful job run | `924260566709944` |
| MLflow run | `ee3b1fdb33814d57b1f13f1cce754e4c` |
| SQL warehouse | `ece93a7877e9e544` (`Serverless Starter Warehouse`) |

The job creates ten `bronze_<csv-name>` Delta tables and two derived tables:
`silver_supplier_week` (6,240 rows) and `silver_material_week` (2,080 rows).
All tables carry a release identifier. Table history is available through
`DESCRIBE HISTORY workspace.halcyon.<table>`.

## Checks that passed

- Explicit CSV schemas, required fields, source checksums, row counts, and
  natural-key uniqueness across all ten sources.
- Spark supplier joins preserved 6,240 rows; each material has three suppliers.
- Material mean spot prices agree with the supplied benchmark labels within
  the stated rounding tolerance.
- The organizer baseline has exactly 260 valid IDs, finite forecasts/orders,
  eligible supplier shares, and normalized allocations.
- A separate SQL API query returned 30 supplier rows.
- Serverless job terminated with `SUCCESS`; MLflow run completed with the
  setup counts, source manifest, report, and baseline artifact. The report,
  baseline bytes/checksum, and MLflow metrics were independently retrieved
  through authenticated APIs.

Output files are under
`/Volumes/workspace/halcyon/artifacts/weeks-1-208-18caf03f890c/`:
`setup_report.json` and `baseline_sample_submission.csv`. The latter is an
unchanged organizer baseline, not an improved candidate.

## Local automation and collaboration

Jaseer's machine has Databricks CLI 1.24.0 and a Python 3.12 environment at
`~/.venvs/dsdg-hackathon`. Dependencies are pinned in
[tools/databricks/requirements.txt](../tools/databricks/requirements.txt).
The OAuth profile is `halcyon`; credentials remain outside Git. Non-secret
resource IDs are in `~/.local/share/dsdg-databricks/workspace.json`.

The three teammate accounts supplied by Jaseer were verified active and granted
project folder editing, schema-scoped data access, warehouse usage, job-run
management, and MLflow experiment editing. Direct grants and resource ACLs were
read back and verified for all three users.
No administrator role is assigned by the setup scripts. Each teammate must
authenticate using their own identity to automate the shared workspace.

Review update: AV independently ran setup job `616624441359205` successfully.
All 12 tables remain Delta and the setup job is on-demand with one concurrent
run. Andrew additionally has `CAN_MANAGE` on the existing setup job for Phase 2
redeployment; other teammates retain `CAN_MANAGE_RUN`. The sharing helper
preserves owner/manager rights on later reruns. This is project-scoped access.

Implementation owners, gates and handoffs are in
[the code plan](implementation-plan.md), [contracts](contracts.md), and
[agent index](agents/README.md). The separate
[training job `793929914775702`](https://dbc-7e1d4af4-7a60.cloud.databricks.com/jobs/793929914775702)
now runs the pipeline; the setup job remains infrastructure evidence.
Andrew retains `IS_OWNER`; Tejas and AV have `CAN_MANAGE_RUN`, verified by ACL
readback. Jaseer's existing workspace administrator access was unchanged.
Schema ownership alone did not permit reading Andrew-owned gold tables;
Jaseer now also has explicit schema-scoped `SELECT`. A real SQL query then
verified 130 unique forecasts and 130 unique decisions in each scoring window.

Training job run `352305866720915` was independently verified `SUCCESS`.
Its MLflow run `c0001ec0e4c847b3821ad74c3bf422b2` in `/Shared/halcyon/runs`
exported 260 rows from release `weeks-1-208-18caf03f890c`, with source Delta
versions pinned at 1. Downloaded CSV SHA-256:
`3f5a17f3d2b774938c6b13e7cf6fb4c19138831782fa4db702118a830a8d486c`.
This is an unevaluated **provisional baseline**, not the final candidate or an
external submission. Run artifacts are under
`/Volumes/workspace/halcyon/artifacts/runs/c0001ec0e4c847b3821ad74c3bf422b2/`.

Rerun, without provisioning or changing job settings:

```bash
databricks jobs run-now 408041045566144 --no-wait --profile halcyon
```

Source and provisioning/sharing instructions: [tools/databricks/README.md](../tools/databricks/README.md).
