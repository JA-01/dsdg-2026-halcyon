# Situation at cutoff 221

Released evidence only; forecast window 222–234. Warnings and announcements are not certain shocks.

Weeks 209–221 contained 9 disrupted weeks for lithium and 3 each for cobalt,
copper and natural_gas. These released outcomes are held-out evaluation only,
not a source for model selection. Tariff schedules below can still be reversed.

| Material | State / age (weeks) | Future tariffs | Active warning templates | Supplier hits now |
|---|---|---|---|---|
| lithium | 0 / 1 | — | — | — |
| cobalt | 0 / 7 | — | T15, T07, T08 | — |
| copper | 0 / 7 | — | — | — |
| aluminum | 0 / 25 | KES@224:35% | T01, T04, T15, T03 | — |
| steel | 0 / 41 | — | T15 | — |
| rare_earths | 0 / 24 | — | T06, T15 | — |
| semiconductors | 0 / 41 | KES@224:35% | T15 | — |
| polymer_resin | 0 / 41 | — | T15 | — |
| specialty_glass | 0 / 41 | — | T15 | — |
| natural_gas | 0 / 7 | — | — | — |

State 1 = disrupted. + = run began before observed history. Supplier hit: capacity <90% normal or lead above base; ratios/delay shown. Warnings: last12 weeks, excluding reports preceding a known recovery/cancellation.

- T01: Importers watch {} trade dispute closely
- T03: {} confirms new duties on {} {}
- T04: Tariff schedule on {} {} published
- T06: Lawmakers in {} debate limits on raw material exports
- T07: {} ministry calls {} a strategic priority
- T08: {} {} exporters report slower license approvals
- T15: Tensions rise between {} and neighbors

Primary remains the base expectation; the shock hedge is an intentionally aggressive MERROW/event scenario. Small, correlated event samples do not establish causality.

## Evaluation — local estimates, not official scores

Selection uses origins 65,78,…,195 only. Halving calm-state near-term risk lifts
mean clipped Brier skill 0.3142→0.3314 and primary mean score 48.612→48.922;
best-of-two mean 52.625→52.940, worst 33.183→33.154. Selected in `3280969`
before the one-time held-out evaluation; active-shock forecasts are unchanged.

| Held-out weeks 209–221, cutoff 208 | Score | Raw Brier skill |
|---|---:|---:|
| Before calm shrinkage | 61.318 | 0.1234 |
| Selected primary | 61.109 | 0.1118 |
| Selected shock hedge | 57.544 | −0.1219 |
| Robust probabilities / primary policy | 60.712 | 0.0898 |

Reference is the unchanged organizer sample; opening stock is 5× first-week
demand. The held-out primary regression is −0.209 points; it did not change
selection or parameters. Final private forecasts train through 221. These
estimates do not claim a new Kaggle result or authorize any upload.
