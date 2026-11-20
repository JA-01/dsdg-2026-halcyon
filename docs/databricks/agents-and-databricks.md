# How LLMs can work with Databricks without computer control

Researched November 6, 2026 using Databricks documentation and Databricks-maintained source. This is an implementation recommendation, not a tested connection to the team's workspace. The Databricks CLI is not installed in the current local environment, and no workspace credentials or workspace URL were supplied for this task.

> Written on Friday night, before the build. We followed its recommendation: the agents drove Databricks through the CLI and Python SDK (see [`tools/databricks/README.md`](../../tools/databricks/README.md)).

## Recommendation

Start with **a local coding assistant using the Databricks CLI and Python SDK**. The assistant writes normal source files, uploads them, launches a serverless notebook job, checks execution state, queries Delta outputs, and reads MLflow metrics. A person completes the initial sign-in/consent; routine work then runs programmatically. Databricks' CLI wraps its REST APIs, so this does not require navigating the website. See [CLI overview](https://docs.databricks.com/aws/en/dev-tools/cli/).

Use MCP as an optional tool interface, not the only way to make progress. The current SQL MCP requires an account-admin beta enablement, whereas Free Edition has no account-console access. This is a concrete reason to test availability before depending on it, not proof that every MCP is unavailable in Free Edition. See [SQL MCP prerequisites](https://docs.databricks.com/aws/en/agents/mcp-tools/databricks-sql) and [Free Edition limitations](https://docs.databricks.com/aws/en/getting-started/free-edition-limitations).

There are two distinct uses of an LLM here:

- **Development/operation:** the coding assistant creates tables, runs Spark code, launches experiments, and fixes errors through tools. This is the primary answer to avoiding computer control.
- **Inside the product:** an optional LLM extracts synthetic news events or explains saved forecasts through bounded functions. It does not need general workspace administration or permission to invent order quantities.

## Options and their role

| Interface | What an LLM-equipped system can do | Recommendation / constraints |
| --- | --- | --- |
| Databricks CLI | Manage workspace files, copy Volume files, create/run jobs, inspect runs; structured output | First choice for the development assistant; simple tool calls from a terminal |
| Python SDK (`databricks-sdk`) | Automate workspace resources, SQL statements, file access, and job lifecycle with typed Python objects | First choice for repeatable orchestration or narrow application tools |
| SQL Statement Execution API | Send SQL to a warehouse and poll/fetch results over REST | Good for inspecting Delta tables, aggregations, and dashboard/chat data access; not a general Python runtime |
| Databricks Connect | Write PySpark locally and execute Spark plans on remote compute | Useful for interactive feature development; adds runtime/Python compatibility work |
| Databricks-managed MCPs | Give MCP clients callable data/tools with Unity Catalog permissions | Optional; check the exact server's prerequisites, permissions, and auth |
| Databricks agent skills | Give the assistant Databricks workflow instructions | Useful supplement; skills alone do not supply authentication or remote execution |
| AI Dev Kit standalone MCP | Expose Databricks actions through a locally operated MCP server | Alternative if MCP is needed; extra installation and best-effort maintenance |

The [Python SDK guide](https://docs.databricks.com/aws/en/dev-tools/sdk-python) covers local and notebook use and recommends pinning the tested SDK version. [Databricks Connect](https://docs.databricks.com/aws/en/dev-tools/databricks-connect/) sends Spark work remotely while ordinary client Python runs locally; it does not turn every local Python statement into remote execution. Its [requirements](https://docs.databricks.com/aws/en/dev-tools/databricks-connect/requirements) include compatible compute/client versions, Unity Catalog, and Python requirements.

## 1. Practical CLI/SDK workflow

Use a current supported Databricks CLI rather than the legacy Python CLI package. Installation guidance: [install the CLI](https://docs.databricks.com/aws/en/dev-tools/cli/install). The following are illustrative commands for the **future implementation**; the notebooks, catalog/schema, Volume, job, and artifacts do not exist in this repo yet.

### Bootstrap and authentication

```bash
databricks version
databricks auth login --host 'https://<workspace-host>' --profile halcyon
databricks current-user me --profile halcyon --output json
databricks warehouses list --profile halcyon --output json
```

OAuth user authentication lets the supported tools manage tokens/refresh after user sign-in. Use a workspace-level host, not account-level APIs. Keep the named profile and token cache outside the repository; do not print tokens into assistant logs. Check the actual Free Edition authentication flow before promising unattended operation. See [OAuth user authorization](https://docs.databricks.com/aws/en/dev-tools/auth/oauth-u2m).

### Upload inputs and notebooks

Create a team schema and managed Volume through SQL/SDK once privileges are confirmed. Then, for example:

```bash
databricks fs cp data/ 'dbfs:/Volumes/<catalog>/halcyon/raw/phase1/' --recursive --profile halcyon
databricks workspace import-dir notebooks/ /Workspace/Shared/halcyon/notebooks --profile halcyon
```

The `dbfs:/Volumes/...` spelling is the **CLI URI for a Unity Catalog Volume**, not a requirement to use legacy DBFS-root storage. Notebook Python can reference `/Volumes/<catalog>/halcyon/raw/phase1/`. Workspace source belongs in workspace paths, not a Volume pretending to be a notebook. See [filesystem commands](https://docs.databricks.com/aws/en/dev-tools/cli/reference/fs-commands) and [workspace commands](https://docs.databricks.com/aws/en/dev-tools/cli/reference/workspace-commands).

### Execute and inspect

Create a saved serverless notebook job from a reviewed JSON definition, using notebook-scoped dependencies and explicit catalog/schema/release/cutoff parameters. Do not copy a classic-cluster example that requires a cluster ID. The job definition must be created and validated against the workspace during implementation.

```bash
databricks jobs create --json @job.json --profile halcyon --output json
databricks jobs run-now '<job-id>' --no-wait --profile halcyon --output json
databricks jobs get-run '<run-id>' --profile halcyon --output json
databricks jobs get-run-output '<task-run-id>' --profile halcyon --output json
```

Poll using returned IDs until execution reaches a terminal state, then check success/error rather than treating “request accepted” as a completed run. For multi-task jobs, retrieve task IDs from the parent run before asking for task output. Save substantive outputs to Delta, MLflow, or a Volume instead of depending on notebook stdout. See [job commands](https://docs.databricks.com/aws/en/dev-tools/cli/reference/jobs-commands).

Python automation can share the profile:

```python
from databricks.sdk import WorkspaceClient

workspace = WorkspaceClient(profile="halcyon")
for warehouse in workspace.warehouses.list():
    print(warehouse.id, warehouse.name)
```

An assistant's useful iteration loop is: edit source → upload → launch → inspect failure or metrics → fix → rerun. Ask it for a run ID, data checks, and the exported artifact each time. This makes its actions and results reviewable without screenshots.

## 2. SQL access for an application or analytics tool

Use `workspace.statement_execution.execute_statement(...)` or `POST /api/2.0/sql/statements` with the warehouse ID. The response supplies `statement_id` and status; poll `GET /api/2.0/sql/statements/{statement_id}` and fetch remaining chunks when applicable. A successful HTTP response can still contain a failed/canceled SQL execution. Use named parameter markers for user values, fixed/allowlisted identifiers, result limits, and a bounded wait/cancel policy. See [Statement Execution API](https://docs.databricks.com/api/statement-execution/v1/execute-statement).

For this project, prefer purpose-built functions over passing unrestricted LLM SQL through:

| Proposed tool | Input | Result / implementation |
| --- | --- | --- |
| `get_material_risk` | Material, target week, run ID | Fixed query of saved forecast + evidence rows |
| `explain_order` | Material, week, run ID | Saved quantity/shares, inventory assumptions, supplier/forecast evidence |
| `compare_runs` | Two run IDs | MLflow metrics and backtest artifacts |
| `start_pipeline` | Valid release ID, cutoff, approved config | Starts one known job; returns run ID |
| `get_pipeline_status` | Run ID | State, error summary, output artifact references |

These are proposed application contracts, not existing Databricks tool names. Keep the in-product explanation tools read-only; give the development assistant the schema/job write access needed for implementation. Return concise structured results and explicit missing-data errors. Treat news bodies as data, not instructions to operate the workspace.

## 3. MCP and Databricks skills

Databricks provides managed MCPs for tool access and separate agent skills for workflow knowledge. Its [MCP overview](https://docs.databricks.com/aws/en/agents/mcp-tools) distinguishes SQL-oriented development tools from natural-language business analytics. Skills can be installed through a recent CLI:

```bash
databricks aitools list
databricks aitools install --scope project
```

Review the selected tools and any repository config changes when doing the actual setup. These commands are research instructions; no skills/plugins were installed during this task. See [official agent skills](https://docs.databricks.com/aws/en/agent-skills/).

The currently documented SQL MCP endpoint is:

```text
https://<workspace-hostname>/ai-gateway/mcp-services/system.ai.dbsql
```

It executes SQL asynchronously and permits reads/writes by default under Unity Catalog permissions. Its documented policy can disallow writes. Confirm Unity Gateway beta access first, configure the client using the current Databricks guide, and prove `SELECT 1` works before expanding scope. Do not equate a SQL MCP with arbitrary Python/Spark notebook execution. See [SQL MCP](https://docs.databricks.com/aws/en/agents/mcp-tools/databricks-sql).

The [AI Dev Kit repository](https://github.com/databricks-solutions/ai-dev-kit) from Databricks Field Engineering still includes a standalone MCP server, maintained on a best-effort basis. Its current recommendation is official CLI-installed skills; older tutorials using the retired plugin or bundled skill layout may be stale. Use its standalone server only if the team specifically needs that interface and verifies its tools against serverless compute. It is not the same deployment as a Databricks-managed MCP.

## 4. Where product LLM calls and MLflow fit

The first product LLM task should be structured event extraction from the supplied news. Run it in the notebook driver if a usable endpoint/network path exists; otherwise run extraction locally and upload cached JSON/CSV for Spark ingestion. Never call the LLM independently on every Spark row or put internet calls inside a serverless Spark UDF. The latter cannot access the internet. See [serverless limitations](https://docs.databricks.com/aws/en/compute/serverless/limitations).

Do not make access to one hosted foundation model a prerequisite. Cache by full input + model + prompt version, preserve per-article availability, validate outputs, and use a deterministic extraction fallback. Keep forecasting and order optimization in tested numerical code; the LLM can explain results using retrieved evidence.

Use MLflow first for conventional experiment tracking: forecast/policy configuration, backtest metrics, model artifacts, and final CSV provenance. Optional MLflow tracing can then record the extraction/explanation inputs, outputs, timing, tool calls, and available token usage, making the LLM component demonstrable. See [MLflow tracking](https://docs.databricks.com/aws/en/mlflow/tracking) and [MLflow tracing](https://docs.databricks.com/aws/en/mlflow3/genai/tracing/overview).

## 5. Workspace smoke test and fallback decisions

Perform this before investing in optional integrations:

1. Authenticate once; confirm the current user and list the workspace's available warehouse/catalog.
2. Upload a tiny CSV to a managed Volume; run Spark to create/read one Delta table and inspect its history.
3. Create one MLflow experiment/run and retrieve its metric from outside the notebook.
4. Run a saved serverless notebook job through CLI/SDK and retrieve its output artifact.
5. Only then test optional Connect, MCP, and hosted LLM access. Record versions, permissions, and actual results.

| Failure | Response |
| --- | --- |
| Managed SQL MCP needs unavailable admin enablement | Use the SDK/SQL API and CLI jobs; no MCP dependency in P0 |
| Local Connect has version/auth problems | Execute Spark in the notebook job; keep local orchestration via CLI |
| Workspace cannot reach an external LLM provider | Extract locally and persist results into Delta, or use rule-based features |
| Optional package/model endpoint is unavailable | Use scikit-learn and deterministic news features |
| Free Edition compute quota is exhausted | Preserve/export artifacts early, use local iteration while waiting, and demo clearly labeled prior Databricks results |
| Initial workspace auth or permissions fail | Resolve access with the workspace owner; do not assume APIs bypass permissions |

**Decision:** implement the CLI + SDK job path first, with Delta/Spark/MLflow as visible pipeline components. Add Databricks skills for development help and MCP only after its workspace prerequisites pass. No browser automation is needed for the normal development loop.
