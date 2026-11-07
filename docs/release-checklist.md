# Halcyon release checklist

**This is a delivery gate, not a declaration that the release is complete.**
An unchecked item is pending/unconfirmed. Checked items below refer only to the
named evidence, not approval of a final submission. Andrew owns integration,
run artifacts and the final candidate manifest; Jaseer/designated humans own
external confirmations. Owners must attach the actual run/hash or receipt when
closing a gate. Do not infer upload/selection from prepared code or files.

Sources: [competition rules](../kaggle_instructions.md),
[participant cheat sheet](<../Participant Cheat Sheet (share with teams).md>),
[organizer video email](../emails.md), [contracts](contracts.md).
All deadlines are **America/Chicago (Central)** in 2026.

## 1. Existing baseline evidence — not candidate approval

- [x] Real provisional pipeline reference supplied: job
  [793929914775702](https://dbc-7e1d4af4-7a60.cloud.databricks.com/jobs/793929914775702),
  job run [352305866720915](https://dbc-7e1d4af4-7a60.cloud.databricks.com/?o=7474644438221407#job/793929914775702/run/352305866720915);
  Jaseer's acceptance review independently read `SUCCESS`.
- [x] Retrieved manifest/report identify MLflow run
  `c0001ec0e4c847b3821ad74c3bf422b2` in `/Shared/halcyon/runs`, source release
  `weeks-1-208-18caf03f890c`, source Delta versions 1, cutoff 208,
  `provisional_origin_naive` and `provisional_capacity_split`.
- [x] Downloaded exact CSV passes the submission CLI: 260 rows, SHA-256
  `3f5a17f3d2b774938c6b13e7cf6fb4c19138831782fa4db702118a830a8d486c`.
  Its manifest says `score_status: not_evaluated`.
- [x] Jaseer independently read MLflow `FINISHED` and queried **130 unique
  rows per window per gold table** for this baseline.

Artifacts: `/Volumes/workspace/halcyon/artifacts/runs/<run_id>/` contains
`submission.csv`, `forecasts.csv`, `decisions.csv`, `manifest.json`,
`validation_report.json`. Local reference copies are under
`outputs/demo-source/c0001ec0e4c847b3821ad74c3bf422b2/`.
Gold tables are `workspace.halcyon.gold_forecasts` and `gold_decisions`, keyed
by `(run_id, window_id, target_week, material)`. Do not substitute the separate
setup run, unchanged sample CSV, or AV's local proxy evaluation as candidate
MLflow evidence. No candidate/forecast/policy backtests are established in this
baseline run.

### Connected policy candidate and separate development comparison

- [x] Policy candidate `74752ffecc3449e29dfd7494ed47ad80`, job run
  `1098642218506545`, independently read `SUCCESS`; real Delta input,
  `inventory_cover` policy and still-provisional `provisional_origin_naive`
  forecast. Downloaded 260-row CSV SHA-256:
  `734c30db0566c6968a43bc527958d264533fb22adf248f29f3d22bf825641247`.
- [x] Separate MLflow comparison `16a09a7f38e4484fa6c51e678bbee2cd` independently
  read `FINISHED`; downloaded config/backtests/summary show local-CSV proxy
  comparisons at origins 130/156. Inventory cost improves in three windows and
  regresses 0.96% in 157–169. Forecast skills remain zero by construction.
- [ ] Close comparison reproducibility gaps: source hashes, complete code
  identity, per-window assumptions and package/config versions. Existing
  comparison Git SHA predates its implementation; do not imply full lineage.
- [ ] Replace provisional forecasting only after actual forecasting-owner
  handoff and controlled forecast-only/combined evidence.


## 2. Code and evidence gates — integration owner

### Historical selection and correctness

- [ ] Integrate actual forecasting and policy components through the shared
  interfaces; record exact model/policy configuration and any explicit fallback
  reason. Provisional code/export success alone does not close this gate.
- [ ] Confirm point-in-time inputs and training labels at every outer/inner
  origin; only known future demand is permitted beyond cutoff. Keep evaluator
  future prices, shocks and realized supply out of forecast/policy inputs.
- [ ] Compare baseline, forecast-only, policy-only and combined changes on
  **development origins 130/156**, using fresh origin-specific naive baselines,
  not week-208 sample values. Log real Brier/MAPE and raw/proxy policy costs,
  overall/shock-recovery fill and diversification, including regressions.
- [ ] Select settings before unlocking **holdout origin 182 (183–208)**;
  evaluate once without holdout tuning. Preserve both 13-week subwindows and
  separately report horizons 1–13 relevant to Phase Two.
- [ ] Confirm both windows forecast from the same origin in each Phase One-style
  fold, plan independently, and start with fresh five-week stock/zero transit.
  Record simulator assumptions and sensitivity; missing organizer parity or
  financial normalizers mean proxy metrics, never a fabricated official score.

### Real runs, Phase Two and exact bytes

- [ ] Log a real baseline/candidate comparison in `/Shared/halcyon/runs`, with
  release/checksums, pinned Delta versions, code/config/package versions, seed,
  cutoffs, window identities, metrics and artifacts. Capture an actual Spark
  transformation and Delta history, not just a screenshot of source code.
- [ ] **Pending external prerequisite:** obtain genuine Phase Two release
  through week 221 after **Saturday November 7, noon**. Ingest a new immutable
  release and pin its source versions. Do not fabricate release data or mark
  the real refresh complete based on synthetic fixtures/code paths.
- [ ] Refresh private forecasts/orders for **222–234 at cutoff 221**, with fresh
  stock and no transit. Keep validated archived Phase One public **209–221**
  rows, original cutoff/run ID and checksum. Newly released public truth is
  not fresh validation, and no public stock/transit carries into private.
- [ ] Export one real CSV, header/no index, all **260 unique sample IDs** in
  sample order, canonical 10 columns. Validate finite/ranged probabilities,
  positive prices, nonnegative orders, eligible shares and sums within `1e-6`,
  including zero-order rows. Reread/validate exact exported bytes; no repair
  by silent clipping or renormalization.
- [ ] Preserve exact final CSV/hash and manifest/report in the run Volume and
  MLflow; check run-scoped gold outputs and archived/new block provenance agree.
- [ ] Freeze the owner-managed final candidate manifest for **up to two**
  candidates plus a known-good fallback, with run IDs, exact checksums,
  comparison basis, limitations and explicit selection status. Preserve earlier
  artifacts; do not label a future candidate verified using this baseline's hash.

### Demo and evidence handoff

- [x] Run the exact [demo command](demo/README.md#notebook-and-local-entrypoint)
  against downloaded policy candidate `74752ffecc3449e29dfd7494ed47ad80`
  and comparison `16a09a7f38e4484fa6c51e678bbee2cd`; retained the report
  and trace/comparison CSVs. Tampered hash and divergent decision smoke inputs
  were rejected.
- [x] Execute the deployed demo with real pinned Delta/Spark, gold and MLflow
  reads: submit run `282966950685740` terminated `SUCCESS`; persisted report
  verifies exact export and 260 matching forecasts/decisions.
- [x] Show separate proxy comparisons, including the cost/fill regressions.
  No official score, leaderboard gain, LLM benefit or simulator parity claimed.
- [x] Produce an approximately three-minute methodology artifact:
  `outputs/demo-video/Bay-Area-Builders-methodology.mp4`, 185.05 seconds,
  H.264/AAC 1920×1080, SHA-256
  `74bf5a020ac5a458e11f3cb7fdee3ffacc01e37282679138cfa395358d31d0bc`.
  Generated slides/synthetic voiceover describe this policy candidate, not a
  future forecasting model. Visual frames and audio signal were checked.
- [ ] Human reviews the video against the final selected methodology and
  approves or replaces the provisional-forecast narration before uploading.

## 3. Human-only external actions — never implied by code

| Deadline | Required human action | Completion evidence |
| --- | --- | --- |
| Before first submission | Each person joins; merge the **1–4 person team on Kaggle** | Team page/member confirmation |
| Every submission day | Check shared team budget: **maximum 5 submissions/team/day** | Count used/remaining attempts before upload |
| Sat Nov 7, **6 PM** | Submit [Databricks track opt-in form](https://docs.google.com/forms/d/e/1FAIpQLSfst7f3Ay_CILsIJjm2fznPy41CplIDS_nBd-wCVVlPrsghow/viewform) | Form confirmation/receipt |
| Sun Nov 8, **noon** | Upload chosen exact validated CSV(s) to [Kaggle](https://www.kaggle.com/competitions/dsdg-hackathon-2026-supply-chain-disruptor) | Accepted submission IDs mapped to run IDs and hashes |
| Sun Nov 8, **noon** | Explicitly select **up to 2 final submissions** | Kaggle final-selection page confirmation |
| Sun Nov 8, **noon** | Upload **one approximately 3-minute video** to [Bay Area Builders' folder](https://drive.google.com/drive/folders/1iuS0TqxXjXrp5XCcACLQLj_S9tsjRagO) | Uploaded file link, access and playback confirmed |

- [ ] Human confirmed Kaggle team merge before first submission.
- [ ] Human reconciled all teammates' submission attempts; daily limit respected.
- [ ] Human confirmed Databricks opt-in receipt before its deadline.
- [ ] Human matched accepted Kaggle submission IDs to the final run/CSV hashes.
- [ ] Human explicitly confirmed final selections before the deadline. Without
  selection Kaggle defaults to the two best public scores; do not rely on that
  after public weeks become released history.
- [ ] Human uploaded the approved `Bay-Area-Builders-methodology.mp4` (team name
  in filename), then opened the actual uploaded video and checked playback and
  organizer access. The generated local MP4 is not delivery evidence.

Per the cheat sheet, private leaderboard placement contributes 80% and video
judging 20% of final placement. No external action above is confirmed by the
current package. Retain receipts in the team's delivery record, not credentials
or private access tokens in Git.
