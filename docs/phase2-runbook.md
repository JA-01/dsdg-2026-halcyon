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
5. Commit the new `data/*.csv` and both configs, then run them one at a time from a clean checkout. The job allows one run at a
   time, so post on the board before and after. Both runs are named `phase2-private` in MLflow, so tell
   them apart by run ID and config path, and note which run ID belongs to which slot.
   ```bash
   .venv/bin/python -m halcyon.deploy --config configs/phase2_${RELEASE}_slot1_u2.json --run
   .venv/bin/python -m halcyon.deploy --config configs/phase2_${RELEASE}_slot2_u1.json --run
   ```
6. Check each stored run, including that public rows match the archived run exactly. Use the MLflow run
   ID from `task_output`, not the job run ID:
   ```bash
   .venv/bin/python -m halcyon.accept <slot1_run_id> --retained-from 013655b7365d4a01ade8d7c4f15a11be
   .venv/bin/python -m halcyon.accept <slot2_run_id> --retained-from 32244c21c3ed44da8eafda2ed2f4acae
   ```

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

## Rehearsal, November 7

Steps 3 to 6 ran with `--dry-run-cutoff 208` on release `weeks-1-208-18caf03f890c` (Delta versions 1) and
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

What this does not cover: at cutoff 208 the private weeks are horizons 14 to 26, while on Saturday they are
horizons 1 to 13, and real week 221 data does not exist yet. A local throwaway preflight covered that
path on synthetic data, with weeks 209 to 221 copied from 196 to 208. Both slots gave 260 valid rows and
byte-identical public rows at cutoff 221, the full tests passed on the swapped data, and
`bootstrap.py --prepare-only` produced a `weeks-1-221-*` release ID. That data is not real, so it says
nothing about scores. The step 4 check passed correct configs and refused both swapped pairings when run
on configs generated for a test release.
