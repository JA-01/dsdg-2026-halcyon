# Andrew's handoff — integration and release lead

Human Andrew, GitHub `@andrewkwon0804-web`. Jaseer explicitly transferred the
larger integration/release workload to you to conserve his tokens. Read
`AGENTS.md`, plan/contracts and your issues; claim work and post a plan review.

Implement in this order:

1. Shared package, contract definitions/fixtures, configs and dependency pins.
   Merge a small scaffold first; leave Tejas/AV's modules to them.
2. Pinned Delta adapters, cutoff-filtered inputs, forecast requests/windows,
   CSV validator/exporter and MLflow/Volume packaging. Work against fixtures
   while teammates implement their APIs.
3. Connect Tejas's baselines and AV's policy/simulator into a real baseline
   training/export run; then orchestrate model/policy comparisons.
4. Phase 2 ingestion/config rerun, archived-public/new-private lineage, final
   candidate CSVs/checksums/comparisons/fallback and human delivery checklist.
5. Notebook demo, real evidence screenshots/charts and a ~3-minute video script.
6. Optional cached news extraction only after M1. Validate source evidence,
   fictional entities and per-article availability; no external key dependency.

Owned paths are in `AGENTS.md`. Coordinate interfaces/failing tests with Tejas
and AV instead of editing their source. You sequence assigned work, not reassign
people. Do not wait for Jaseer to write the integrator or exporter.

Authenticate as `ak173@illinois.edu` using your own `halcyon` profile. Core
project permissions are granted; you additionally have **CAN_MANAGE** on setup
job `408041045566144` to support Phase 2 redeployment. Invoking the existing
bootstrap is allowed; editing its source requires Jaseer's handoff.

Create a separate `halcyon-pipeline` job and `/Shared/halcyon/runs` experiment.
Share new resources with the team and verify ACLs. Do not replace the existing
setup job with model training. Workspace paths/status are in the setup document.

Completion requires working entry point/config/install instructions; meaningful
invalid-CSV and one-to-one join checks; real baseline/candidate run IDs; exact
CSV bytes/checksums; pinned source/Git/window lineage; a tested Phase 2 path;
and final demo/package/checklist. Prepared artifacts do not prove human uploads.

Review all plans now, especially integration dependencies and public/private
contracts. Correct planning docs by PR and notify affected owners on the board.
