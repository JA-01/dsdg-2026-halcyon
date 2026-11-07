# Lagged disruption response (#78)

Local estimates. Select only origins65,78,…,195; weeks209–221 remain held-out.
Fit a pooled five-coefficient level-response kernel (lags0–4) to one-week
log-price residuals after the existing quote-reversal/slow-reversion forecast.
Regressors are changes in released disruption states, with ridge penalty10.
Each fit target ends by cutoff. Project that kernel over live news probabilities
and subtract its cutoff contribution, avoiding double-counting a current shock.
Only positive projected premiums are added, capped at0.2 log units: forecast
recoveries do not create discounts. Short/incomplete histories keep the previous
forecast. No future news, labels or prices enter inference.

| Selection origins65..195 | Mean MAPE | Mean raw price skill | Worst raw skill |
|---|---:|---:|---:|
| Previous quote reversal | .049783 | .058878 | -.074588 |
| Selected positive lag response | .049502 | .063674 | -.074983 |

Wins7/11, regressions65/117/143/195. Worst MAPE increase .000730 at143.
Clipped price contribution adds .05350 total score points on average. With
unchanged news and policy (123c094), total mean49.862717→49.916214;
worst34.225175→34.219860. These are small, exploratory gains.

Oracle experiment first: fit the same models on released history, supplying
TRUE future disruption states only to forecast the response. The best signed
lag model (lags0–4/penalty10/pooled) gave raw price skill .071950 vs .058878.
With live probabilities, signed responses fell to .050871: uncertain recoveries
caused false price discounts. Positive-only responses fix that issue. Oracle
positive-only at half strength gave .066937; live positive-only at full learned
strength gives .063674. These oracle diagnostics do not use future prices in
fitting and are not production forecasts.

Search: lag lengths4/8/12, ridge1/10, pooled versus material fits shrunk toward
the pool (penalty10); then positive-only strength .25/.5/1 and lags0/4/8 at
penalty10. Material-specific fits and longer lags were worse. Search informed
selection; there is no claim of independent validation on these origins.

Held-out208, evaluated after freeze: MAPE .059610→.058014; price skill
-.032833→-.005193. Both clip to zero, so total remains69.499332. No subsequent
tuning used that window. Private forecasts fit on history through221.

Reproduce the selected comparison:
`.venv/bin/python databricks/price_backtest.py --output /tmp/prices.csv`.
Add `--include-holdout` only for the diagnostic. The committed CSV records all
five candidates and the held-out row. Tests cover future news/label mutation,
learning a delayed synthetic response, not counting an ongoing shock twice,
positive bounded prices and existing cutoff behavior.60 tests pass; primary
and hedge260-row builds validate. AV owns final Databricks runs; no Kaggle upload.
