# Methodology video — approximately 3 minutes

**Team:** Bay Area Builders. Screen directions are not spoken. This version uses
verified policy candidate `74752ffecc3449e29dfd7494ed47ad80` and separate proxy
comparison `16a09a7f38e4484fa6c51e678bbee2cd`. The forecaster is still provisional;
this is not a final-selection or forecasting-improvement claim. Follow the
[runbook](README.md), rehearse, and update evidence if the selected run changes.

## 0:00–0:25 — Problem and working product

*Screen: actual successful pipeline job, then demo identity and checksum.*

“We are Bay Area Builders. Halcyon turns released supply-chain data into disruption
and price forecasts, weekly orders, and a validated competition CSV. This is our
working Databricks inventory-policy candidate. Its forecast is deliberately simple:
historical disruption rates and the last observed benchmark price. We separate
working infrastructure, policy improvement, and forecasting improvement.”

## 0:25–0:55 — Delta, Spark and reproducibility

*Screen: Delta history, pinned Spark market aggregation, MLflow run and artifacts.*

“We pin the release and source Delta versions instead of reading changing latest
tables. Spark joins and aggregates supplier markets at material level. Only
observations available at cutoff enter forecasts and policies; future demand is
the known production plan. MLflow records configuration, source versions, model
and policy identities, and the exact exported CSV. These are actual run outputs,
not a setup-only demonstration.”

## 0:55–1:30 — Signal → forecast → order

*Screen: one material in source signals, forecast/order trace and supplier allocations.*

“Follow this material's last observed benchmark into its price forecast. The
historical disruption rate supplies its risk estimate. Inventory cover uses that
risk, forecast price growth, and recent capacity, lead-time and cost estimates to
plan orders. Supplier preferences balance cost, lead time and diversification,
including shared shipping lanes. Every submitted decision is planned without
future realized arrivals; it cannot secretly adapt to the test window.”

## 1:30–2:05 — Actual comparison, including regression

*Screen: separately identified comparison run, per-window proxy costs and fill.*

“We compare the same forecaster with naive and inventory policies at development
origins 130 and 156. Both thirteen-week windows use the same forecast origin and
fresh inventory. Inventory cover lowers proxy cost in three of four windows,
but raises it about one percent in the calm 157-to-169 window. Forecast skill is
zero by construction. These local-CSV comparisons are logged separately in MLflow;
their incomplete source and code manifest remains a release gate.”

## 2:05–2:35 — Holdout, Phase Two and limits

*Screen: window cutoffs, simulator assumptions and release checklist.*

“Origin 182 stays locked until settings are selected. Phase Two needs the genuine
release through week 221: retain validated archived public rows, then regenerate
private weeks 222 through 234 with fresh stock and no carried transit. Our
financial results are proxies, not the organizer's official score. Material-level
risk cannot name the failed supplier, and shared-lane shocks can hit several
suppliers together.”

## 2:35–3:00 — Exact export and delivery

*Screen: validation report, 260-row header/coverage and exact hash; human checklist.*

“The candidate produced 260 rows, and the downloaded CSV validates against the
organizer's exact IDs and supplier eligibility. The hash links those bytes back
to their run. We claim no leaderboard or LLM improvement. Final forecast evidence,
Phase Two refresh, team selections, track opt-in and actual video upload must be
confirmed separately. Our product shows what ran, the measured tradeoffs, and
what remains unproven.”

## Recording and delivery

Record actual notebook/report and workspace outputs without credentials. Keep
text legible and label offline playback as recorded results. Export one MP4 named
`Bay-Area-Builders-methodology.mp4`. A human uploads it to the
[team video folder](https://drive.google.com/drive/folders/1iuS0TqxXjXrp5XCcACLQLj_S9tsjRagO),
then verifies playback and organizer access by **Sunday November 8, noon
America/Chicago**. A script or local MP4 is not upload confirmation.
