# Phase 2 runbook

Phase 2 data lands Saturday November 7 at noon Central. Every step below is a rerun, with no code or
feature edits. A rehearsal of steps 3 to 6 is recorded at the end.

1. A human downloads the released files from Kaggle (this machine has no Kaggle CLI). Replace
   `data/*.csv` with them, then confirm coverage and that no new headline
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
3. Generate one config per final slot. Both are built whatever the public scores say, because the slots
   are a hedge. `--output` is required here: the default filename uses only the release, so the second
   slot would silently overwrite the first.

   | Slot | Shape | `--like` | `--archive-run` | Archive CSV SHA-256 |
   |---|---|---|---|---|
   | 1 | U2: news, price blend 0.25, cost tilt 3, risk buffer 4 | `configs/phase1_v2_tilt_delta.json` | `013655b7365d4a01ade8d7c4f15a11be` | `9c59e2bcdd5d7099cce8e75fa80ad24bfaeb0eb169b00e85c874a7500136440b` |
   | 2 | U1: news only | `configs/phase1_v2_news_delta.json` | `32244c21c3ed44da8eafda2ed2f4acae` | `59dc988ba37dce62c47a6eb4f18169e8d9ef69fdc14cbc2e191349c87a5f07e3` |

   ```bash
   RELEASE=<release_id>
   .venv/bin/python -m halcyon.phase2 --release $RELEASE --archive-run 013655b7365d4a01ade8d7c4f15a11be --like configs/phase1_v2_tilt_delta.json --output configs/phase2_${RELEASE}_slot1_u2.json
   .venv/bin/python -m halcyon.phase2 --release $RELEASE --archive-run 32244c21c3ed44da8eafda2ed2f4acae --like configs/phase1_v2_news_delta.json --output configs/phase2_${RELEASE}_slot2_u1.json
   ```
4. Check each config against the table. Step 6 compares public rows only, so a config with the wrong
   `--like` would still pass it while its private rows came from the other slot's models and policy.
   Run the [slot check](#slot-check) below with `RELEASE` set. It must print `ok` for both slots.
5. Commit the new `data/*.csv` and both configs, then run them one at a time from a clean checkout. Post
   on the board before and after: the job takes one run at a time and queues a second, but each deploy
   first replaces the shared source, so only the post stops a teammate changing the code under a run.
   Both runs are named `phase2-private` in MLflow, so record each slot's job run ID and MLflow run ID when
   it finishes. Afterwards they differ only by `submission_sha256` and the manifest's `config`. The config
   path is kept only in the job run's parameters.
   ```bash
   .venv/bin/python -m halcyon.deploy --config configs/phase2_${RELEASE}_slot1_u2.json --run
   .venv/bin/python -m halcyon.deploy --config configs/phase2_${RELEASE}_slot2_u1.json --run
   ```
   If deploy crashes or a job fails, look at the job run's state before anything else. The notebook writes
   gold and publishes the CSV before its Spark parity check, so a failed job can leave a published CSV. A
   run from a failed job is not a candidate, even if its file looks valid. Fix the cause on the board with
   the orchestrator, because this runbook allows no code edits.
6. Check each stored run. Use the MLflow run ID from `task_output`, not the job run ID, and a separate
   download directory per slot, because each download is named `submission.csv`:
   ```bash
   .venv/bin/python -m halcyon.accept <slot1_run_id> --retained-from 013655b7365d4a01ade8d7c4f15a11be --download-to outputs/phase2/slot1
   .venv/bin/python -m halcyon.accept <slot2_run_id> --retained-from 32244c21c3ed44da8eafda2ed2f4acae --download-to outputs/phase2/slot2
   ```
   `accept` is not enough alone. It never reads the manifest's cutoff, release or config, and it compares
   parsed public values rather than bytes, so the cutoff-208 rehearsals pass it too. Also run the
   [run check](#run-check) below, which must print `ok` for both slots.
7. Post both slots on the board with their hashes and run IDs for the independent recheck and orchestrator
   review. Humans upload nothing until the orchestrator posts PIPELINE COMPLETE. They then upload each
   CSV unopened, so it isn't re-saved, and select both slots on Kaggle by Sunday noon Central.

Known public outcomes are not new validation. Do not count public weeks as evidence for a candidate.

## Slot check

```bash
.venv/bin/python - "$RELEASE" <<'CHECK'
import json, sys
release = sys.argv[1]
SLOTS = {
    "slot1_u2": ("013655b7365d4a01ade8d7c4f15a11be", "9c59e2bcdd5d7099cce8e75fa80ad24bfaeb0eb169b00e85c874a7500136440b",
                 {"use_news": True, "price_blend": 0.25}, {"config": {"cost_tilt": 3.0, "risk_buffer_weeks": 4.0}}),
    "slot2_u1": ("32244c21c3ed44da8eafda2ed2f4acae", "59dc988ba37dce62c47a6eb4f18169e8d9ef69fdc14cbc2e191349c87a5f07e3",
                 {"use_news": True}, None),
}
for slot, (run, sha, forecaster, policy) in SLOTS.items():
    config = json.load(open(f"configs/phase2_{release}_{slot}.json"))
    assert config["mode"] == "phase2" and config["source"]["release_id"] == release, slot
    assert "cutoff" not in config["source"], f"{slot}: a real run must not set a rehearsal cutoff"
    assert config["archived_public"]["origin_run_id"] == run, f"{slot}: wrong archive run"
    assert config["archived_public"]["sha256"] == sha, f"{slot}: wrong archive hash"
    assert config["forecaster"].get("kwargs") == forecaster, f"{slot}: wrong forecaster kwargs"
    assert config["policy"].get("kwargs") == policy, f"{slot}: wrong policy kwargs"
    print("ok", slot)
CHECK
```

## Run check

Set `RELEASE` and fill in both MLflow run IDs. Run it from the repo root.

```bash
.venv/bin/python - "$RELEASE" <slot1_run_id> <slot2_run_id> <<'CHECK'
import json, sys
from databricks.sdk import WorkspaceClient
release, *runs = sys.argv[1:]
ARCHIVES = {"slot1_u2": "013655b7365d4a01ade8d7c4f15a11be", "slot2_u1": "32244c21c3ed44da8eafda2ed2f4acae"}
w = WorkspaceClient(profile="halcyon")
read = lambda run, name: w.files.download(f"/Volumes/workspace/halcyon/artifacts/runs/{run}/{name}").contents.read()
public = lambda raw: [line for line in raw.splitlines()[1:] if 209 <= int(line.split(b"_")[0][1:]) <= 221]
for (slot, archive), run in zip(ARCHIVES.items(), runs, strict=True):
    manifest = json.loads(read(run, "manifest.json"))
    assert manifest["mode"] == "phase2", f"{slot}: not a Phase 2 run"
    assert manifest["cutoff"] == 221, f"{slot}: cutoff {manifest['cutoff']}, not 221"
    assert manifest["release_id"] == release, f"{slot}: release {manifest['release_id']}"
    assert manifest["config"] == json.load(open(f"configs/phase2_{release}_{slot}.json")), f"{slot}: config differs from the committed file"
    rows = public(read(run, "submission.csv"))
    assert len(rows) == 130 and rows == public(read(archive, "submission.csv")), f"{slot}: public bytes differ from the archive"
    print("ok", slot, run)
CHECK
```

## Rehearsal, November 6 (Central)

Steps 3, 5 and 6 ran with `--dry-run-cutoff 208` on release `weeks-1-208-18caf03f890c` (Delta versions 1) and
no code changes, from commit `deab5792e200a5c3f78b1c4ef1770d752f778027`. The configs are
`configs/phase2_dry_run_slot1_u2.json` and `configs/phase2_dry_run_slot2_u1.json`.

| Slot | Job run | MLflow run | Result CSV SHA-256 |
|---|---|---|---|
| 1 | `1043843386699751` | `9a7d1130c8e649f9947f4dd811758629` | `9c59e2bcdd5d7099cce8e75fa80ad24bfaeb0eb169b00e85c874a7500136440b` |
| 2 | `297268591534455` | `3e8cddd9dbfd432696843b8774353356` | `59dc988ba37dce62c47a6eb4f18169e8d9ef69fdc14cbc2e191349c87a5f07e3` |

Both jobs succeeded with no fallback and `halcyon.accept --retained-from` passed all 11 checks. Each CSV has
260 valid rows and its 130 public rows are byte-identical to its archive. Each whole file also equals its
archive, because at cutoff 208 the private rows are planned from the same data as Phase 1. These runs are
labeled not-a-candidate and are not new submissions.

The slot check and the run check are written for a real release, so both refuse these rehearsal runs by
design. The slot check passed correct configs generated for a test release and refused swapped pairings.

What this does not cover:

- **Horizons 1 to 13 in the private window.** At cutoff 208 the private weeks are horizons 14 to 26, which
  use the reference rate instead of the news lift. On Saturday they are horizons 1 to 13, so these
  rehearsal rows never used the lift. Only Phase 1's public window has run that path on real data.
- **A local preflight covered part of that, on synthetic data.** With weeks 209 to 221 copied from 196 to
  208, both slots gave 260 valid rows and byte-identical public rows at cutoff 221, the full tests passed on
  the swapped data, and `bootstrap.py --prepare-only` produced a `weeks-1-221-*` release ID. It used local
  CSVs, and because the data is not real it says nothing about scores.
- **Nothing has run on Databricks with Phase 2 data.** That leaves the setup job on new data, Delta reads
  at table versions other than 1, Spark feature parity at cutoff 221, and news events from Delta. These
  come first on Saturday, so allow time before the Sunday noon deadline.
