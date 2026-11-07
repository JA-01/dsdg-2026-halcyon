# Situation at cutoff 221

Released evidence only; forecast window 222–234. Warnings and announcements are not certain shocks.

| Material | State / age (weeks) | Future tariffs | Active warning templates | Supplier hits now |
|---|---|---|---|---|
| lithium | 0 / 1 | — | — | — |
| cobalt | 0 / 7 | — | T15, T07, T08 | — |
| copper | 0 / 7 | — | — | — |
| aluminum | 0 / 25 | KES@224:35% | T01, T04, T15, T49, T03 | — |
| steel | 0 / 41 | — | T15 | — |
| rare_earths | 0 / 24 | — | T06, T15 | — |
| semiconductors | 0 / 41 | KES@224:35% | T15 | — |
| polymer_resin | 0 / 41 | — | T15 | — |
| specialty_glass | 0 / 41 | — | — | — |
| natural_gas | 0 / 7 | — | — | — |

State 1 = disrupted. + = run began before observed history. Supplier hit: capacity <90% normal or lead above base; ratios/delay shown. Warnings: last12 weeks, refreshed within4 (live-model expiry), after known recovery/cancellation.

- T01: Importers watch {} trade dispute closely
- T03: {} confirms new duties on {} {}
- T04: Tariff schedule on {} {} published
- T06: Lawmakers in {} debate limits on raw material exports
- T07: {} ministry calls {} a strategic priority
- T08: {} {} exporters report slower license approvals
- T15: Tensions rise between {} and neighbors
- T49: Trade talks between {} and {} stall

The hedge is an authorized KES-ban hypothesis from week224: KES capacity x0.37; its materials have a probability floor0.6. These are scenario judgments, not a KES-specific backtest optimum.

## Projected decision changes

Snapshot `947c48f`, scenario frozen in `de6ef49`: 63 private rows change,
including 55 probability rows. Public rows are byte-identical; primary bytes
are unchanged. Order-weighted KES shares for orders placed from week224:

| Material | Primary | Hedge |
|---|---:|---:|
| lithium | 62.6% | 47.3% |
| cobalt | 66.2% | 43.0% |
| aluminum | 49.9% | 48.2% |
| steel | 97.1% | 52.0% |
| rare_earths | 71.6% | 46.4% |
| semiconductors | 9.5% | 9.5% |
| polymer_resin | 62.6% | 44.3% |

Eligibility comes from suppliers.csv: seven KES materials, not SUN-only glass.
The LP also pre-buys steel, rare_earths and polymer_resin before224.
No KES/VAL selection origin confirms the haircut size. On65..195 this dated
scenario is inactive: pair mean49.863/worst34.225, versus53.931/34.225 with
the old stress hedge. AV accepted that historical regression for this private bet.

One frozen held-out208 check: hedge69.499 local (P.3212/F.8190/R.9034), identical
to the primary because public rows are unchanged. Reference: organizer sample;
opening stock5× first-week demand. Private outcomes are unknown. Byte parity
is not a new Kaggle receipt, and no upload was performed.
