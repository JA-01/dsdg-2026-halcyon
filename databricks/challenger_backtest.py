"""python databricks/challenger_backtest.py --output /tmp/challenger.csv"""
import argparse
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from halcyon import disruption, price, policy, policy_challenger, score, submit
from halcyon.data import read_all


def evaluate(tables):
    rows = []
    for name, planner in [('live_ensemble', submit.plan_window),
                          ('primary', lambda t,c,w: submit.plan_window(
                              t,c,w,(disruption.predict, price.predict, policy.plan))),
                          ('challenger', lambda t,c,w: submit.plan_window(
                              t,c,w,(disruption.predict, price.predict, policy_challenger.plan)))]:
        result = score.backtest(tables=tables, planner=planner)
        result['candidate'] = name
        rows.append(result)
    return pd.concat(rows, ignore_index=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', default='data')
    parser.add_argument('--output', type=Path, default=Path('/tmp/challenger.csv'))
    args = parser.parse_args()
    result = evaluate(read_all(args.data_dir))
    result.to_csv(args.output, index=False)
    print(result.groupby('candidate').agg(mean=('score','mean'), worst=('score','min'),
          F=('F','mean'), fill_skill=('fill_skill','mean'), diversification=('diversification','mean')).to_string())
