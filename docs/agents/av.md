# AV's handoff — simulator and ordering

Human AV, GitHub `@AV-01`. Own `halcyon/simulator.py and halcyon/policy.py`, matching
tests/notebooks and `docs/simulator-assumptions.md`. Your independent setup run
already passed; do not repeat it. Read rules/plan/contracts, claim your issue
and post a review.

First implement `simulate_window(...)` and `Policy.decide(...)` as contracted, with a
naive policy reconstructed at each historical cutoff and a diversified
inventory-cover alternative. Merge working basics before a larger optimizer.
Use fixtures so Andrew can wire the baseline early.

Simulate independent supplier capacity caps, cancelled unpaid slices, landed
purchase costs, lead-time arrivals, demand, holding/shortage costs and terminal
stock/transit salvage. Every window resets five-week stock and zero transit.
Never carry public inventory to private or reallocate cancelled slices silently.

Document unresolved rules: varying-demand initial units, average cost reference,
arrival/holding timing, rounding and hindsight/diversification aggregation.
Use a provenance-identified starter simulator if accessible. Otherwise choose
named configurable assumptions and sensitivity; send precise organizer questions
to Jaseer on the board for human clarification. Do not block a local baseline.

Policies see only history/forecasts and known demand, not future realized
capacity, cost, arrivals or shock labels. Plan the whole submitted horizon.
Use eligible suppliers and correlated lanes; shares normalize even at zero
orders. Distinguish organizer sample from origin-safe historical naive rules.

Meaningful tests: window resets; capped/cancelled orders; arrival timing;
stockout and holding cost; beyond-window transit salvage; infeasible policies;
supplier eligibility/share sums. Return weekly state/costs, raw/proxy metrics,
assumptions and score status. No fabricated official score without parity.

Handoff to Andrew: APIs/config, sample frames, assumptions, tests and fold
cost/fill/concentration comparisons including four-week shock recovery tails.
Coordinate forecast inputs with Tejas; do not rewrite his modules or export.
Review all plans now for simulator/scoring/causal-policy defects, correct docs
by PR and notify affected owners.
