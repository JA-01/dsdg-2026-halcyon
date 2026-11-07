"""Exercise real Spark features against pandas on local source CSVs.

python notebooks/forecasting/spark_smoke.py --output outputs/spark-features
Requires a local PySpark/Java runtime; neither is needed by Forecaster.predict.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

import numpy as np
from pyspark.sql import SparkSession

from halcyon.data import Dataset, SCHEMAS
from halcyon.forecasting.features import build_features
from halcyon.forecasting.spark import build_spark_features


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default="data")
    parser.add_argument("--output", default="outputs/spark-features")
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    os.environ["PYSPARK_PYTHON"] = sys.executable
    spark = (SparkSession.builder.master("local[2]").appName("halcyon-feature-smoke")
             .config("spark.sql.shuffle.partitions", "2")
             .config("spark.pyspark.python", sys.executable).getOrCreate())
    try:
        types = {"str": "STRING", "int64": "BIGINT", "Int64": "BIGINT", "float64": "DOUBLE"}
        tables = {name: spark.read.schema(", ".join(f"{column} {types[kind]}" for column, kind in schema.items()))
                  .option("header", True).option("multiLine", True).option("escape", '"')
                  .csv(str(Path(args.data)/f"{name}.csv")) for name, schema in SCHEMAS.items()}
        weeks = [131, 143, 144, 156]
        result = build_spark_features(tables, 130, weeks, run_id="local-spark-smoke",
                                      release_id="local-csv", window_id="dev130")
        actual = result.toPandas().sort_values(["target_week", "material"]).reset_index(drop=True)
        expected = build_features(Dataset.from_csv_dir(args.data), 130, weeks)
        expected = expected.sort_values(["target_week", "material"]).reset_index(drop=True)
        assert len(actual) == 40 and not actual.duplicated(["target_week", "material"]).any()
        assert actual[["target_week", "material"]].equals(expected[["target_week", "material"]])
        numeric = [c for c in expected.select_dtypes(include="number") if c in actual]
        for column in numeric:
            np.testing.assert_allclose(actual[column].to_numpy(dtype=float),
                                       expected[column].to_numpy(dtype=float), rtol=1e-8, atol=1e-8,
                                       err_msg=column)
        actual.to_csv(output/"features.csv", index=False)
        report = {"spark_version": spark.version, "cutoff_week": 130, "target_weeks": weeks,
                  "rows": len(actual), "numeric_columns_compared": numeric,
                  "context_columns": ["run_id", "release_id", "window_id", "feature_version"],
                  "pandas_parity": True}
        (output/"report.json").write_text(json.dumps(report, indent=2)+"\n")
        print(json.dumps(report, indent=2))
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
