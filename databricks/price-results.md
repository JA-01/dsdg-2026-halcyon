# Price experiment (#78)

Local estimates on the agreed 11 rolling origins (65,78,…,195), each forecasting
13 weeks. Only outcomes available at each cutoff enter a model. The same
origin's carry-forward MAPE supplies the skill denominator. U2's price recipe
is reconstructed as 75% last price plus 25% trailing-52-week mean.

Selected: exponential reversion toward the trailing-104-week mean, half-life
26 weeks. Mean MAPE is **0.050150** versus U2 **0.051999** and naive **0.052955**.
Mean raw price skill is **0.052568**, versus U2 **0.016024**. Worst origin skill
is **−0.051559** (origin117), versus U2 **−0.143371**. This candidate beats U2 in
8/11 origins and naive in9/11. Regressions versus U2: origins78,91,169; worst
absolute MAPE increase0.001489 at91. The mean raw price-component difference
is about0.44 score points (12×skill delta), before clipping/interaction with
Brier. This is not an official Kaggle score or a claim of total-score gain.

Exploratory alternatives: futures blends (50%/100%), pooled expanding-origin
ridge log-return models (regularization10/100), and faster mean reversion
(half-lives4/13) regressed or were less consistent. Comparing trailing centers
26/52/104 weeks favored104; medians at104 were slightly worse than means.
These origins informed selection, so this is development evidence, not an
untouched holdout. Phase2 origin208 is still unavailable and will be reported
separately when labels arrive. No tariff adjustment was added: benchmark price
is average spot, whereas duties are applied separately to landed cost.

Reproduce: `python databricks/price_backtest.py --output /tmp/price-results.csv`.
The committed CSV contains every origin for selected/U2/naive. Tests mutate
future outcomes and check identical predictions, check half-life behavior,
and cover short/missing history. The production implementation is22 lines of
logic plus documentation, with no fitted artifacts or new dependency.
