"""python databricks/price_backtest.py --output /tmp/price-results.csv"""

import argparse
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from halcyon.data import as_of, read_all
from halcyon.price import predict


def evaluate(tables, include_holdout=False):
    rows = []
    cutoffs = list(range(65, 196, 13))
    if include_holdout and tables['outcomes'].week.max() >= 221:
        cutoffs.append(208)
    for cutoff in cutoffs:
        data = as_of(tables, cutoff)
        weeks = list(range(cutoff + 1, cutoff + 14))
        forecasts = predict(data, cutoff, weeks)
        history = data['outcomes'].sort_values('week')
        last = history.groupby('material').benchmark_price.last()
        mean = history.loc[history.week > cutoff - 52].groupby('material').benchmark_price.mean()
        joined = forecasts.merge(tables['outcomes'][['week', 'material', 'benchmark_price']],
                                 on=['week', 'material'], validate='one_to_one')
        actual = joined.benchmark_price
        baseline = joined.material.map(last)
        u2 = .75 * baseline + .25 * joined.material.map(mean)
        naive_error = np.mean(abs(baseline / actual - 1))
        center = history.loc[history.week > cutoff - 104].groupby('material').benchmark_price.mean()
        weight = 1 - 2 ** (-(joined.week - cutoff) / 26)
        previous = (1 - weight) * baseline + weight * joined.material.map(center)
        for name, values in [('last', baseline), ('u2', u2), ('slow_reversion', previous), ('reversion', joined.price_forecast)]:
            error = np.mean(abs(values / actual - 1))
            rows.append(dict(cutoff=cutoff, candidate=name, mape=error,
                             price_skill=1 - error / naive_error))
    return pd.DataFrame(rows)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', default='data')
    parser.add_argument('--output', type=Path, default=Path('/tmp/price-results.csv'))
    parser.add_argument('--include-holdout', action='store_true',
                        help='Report origin 208 only after model selection; never tune on it')
    args = parser.parse_args()
    result = evaluate(read_all(args.data_dir), args.include_holdout)
    result.to_csv(args.output, index=False)
    print(result.pivot(index='cutoff', columns='candidate', values='mape').to_string())
    print(result.groupby('candidate').agg(mean_mape=('mape', 'mean'),
                                        mean_skill=('price_skill', 'mean'),
                                        worst_skill=('price_skill', 'min')).to_string())
