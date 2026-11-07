# Agent launch index

Assignments authorized by Jaseer. Read AGENTS.md, the implementation plan and
contracts, then your brief. Post your claim and plan review on the board.
All agents must review the entire plan and fix planning defects through small
PRs; coordinate incompatible APIs and cross-owner source changes first.

| Agent | Handoff | Assigned issues |
| --- | --- | --- |
| Andrew @andrewkwon0804-web | [Integration/release lead](andrew.md) | [#7 shared contracts/data/export/baseline runner](https://github.com/JA-01/DSDG-Hackathon/issues/7), [#12 Databricks integration/comparisons/Phase 2](https://github.com/JA-01/DSDG-Hackathon/issues/12), [#13 final demo/delivery package](https://github.com/JA-01/DSDG-Hackathon/issues/13), [#14 optional news after baseline](https://github.com/JA-01/DSDG-Hackathon/issues/14) |
| Tejas @tbhojo | [Forecasting](tejas.md) | [#10 features/baselines/candidates](https://github.com/JA-01/DSDG-Hackathon/issues/10) |
| AV @AV-01 | [Simulator/policy](av.md) | [#8 simulation/ordering](https://github.com/JA-01/DSDG-Hackathon/issues/8) |
| Jaseer @JA-01 | [Environment/review](jaseer.md) | Existing setup support; [#6 orchestration update](https://github.com/JA-01/DSDG-Hackathon/issues/6) |

#7 and #8 are the existing owner-claimed tasks. Duplicate #9/#11 are closed;
do not implement them independently. Root package halcyon/ and the
Forecaster.predict / Policy.decide APIs adopt the owners' board agreement.
Andrew publishes the concrete Dataset accessor/constants in #7 before consumers
integrate. The runner invokes policy separately for public/private inventory.

Merge order: #7 small scaffold first; #10/#8 baseline increments and #12 adapters
can proceed against fixtures; then wire the real baseline, compare candidates,
refresh Phase 2, and finish #13. #14 is optional and cannot delay core delivery.

Ready-to-send instruction for each human's agent:

> Read AGENTS.md, docs/implementation-plan.md, docs/contracts.md and my brief
> linked above; read tools/board unread; claim my assigned issue; review and fix
> plan defects; implement the smallest mergeable baseline increment in my owned
> paths. Post concrete interfaces, tests, limitations and handoff to the next
> owner. Do not repeat completed setup or edit another owner's source.
