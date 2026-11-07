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

Rerun, without provisioning or changing job settings:

```bash
databricks jobs run-now 408041045566144 --no-wait --profile halcyon
```

Source and provisioning/sharing instructions: [tools/databricks/README.md](../tools/databricks/README.md).
