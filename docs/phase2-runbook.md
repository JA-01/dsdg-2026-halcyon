# Phase 2 runbook

Phase 2 data lands Saturday November 7 at noon Central. Every step below is a rerun, with no code or
feature edits. A rehearsal of steps 3 to 5 is recorded at the end.

1. Replace `data/*.csv` with the released files, then confirm coverage and that no new headline
   template went unclassified:
   ```bash
   .venv/bin/python -m pytest -q
   .venv/bin/python -c "from halcyon.data import Dataset; print(Dataset.from_csv_dir('data').observed_through)"  # 221
   ```
2. Create the immutable snapshot, using the existing setup tooling. It updates the setup job only:
   ```bash
   .venv/bin/python tools/databricks/bootstrap.py --prepare-only
   .venv/bin/python tools/databricks/bootstrap.py
   ```
   Wait for that job to succeed. Its report at
   `/Volumes/workspace/halcyon/artifacts/<release_id>/setup_report.json` pins the table versions.
3. Generate the config. `--like` names the Phase 1 config whose forecaster and policy to use, and
   `--archive-run` names the validated Phase 1 run whose public rows are retained:
   ```bash
   .venv/bin/python -m halcyon.phase2 --release <release_id> --archive-run <phase1_run_id> --like configs/<candidate>.json
   ```
4. Commit that config, then run it from a clean checkout:
   ```bash
   .venv/bin/python -m halcyon.deploy --config configs/phase2_<release_id>.json --run
   ```
5. Check the stored run, including that public rows match the archived run exactly:
   ```bash
   .venv/bin/python -m halcyon.accept <run_id> --retained-from <phase1_run_id>
   ```
   Phase 2 selected starts from `configs/phase1_selected_delta.json` and archive run
   `7d2271940a5744c3bd3756a7071c72c4`; runner-up from `configs/phase1_runner_up_delta.json`
   and `5ef4cf179fd847329e5ac04b2f980149`.

Known public outcomes are not new validation. Do not count public weeks as evidence for a candidate.
