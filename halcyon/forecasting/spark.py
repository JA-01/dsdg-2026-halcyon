"""Native, cutoff-safe Spark counterpart of the pandas feature schema.

PySpark is deliberately imported inside the entry point. This module does not
start a session, collect source tables, call pandas, or use Python UDFs. The
small final validation aggregate is the only action; returned rows can be written
to Delta with all origin/run/version identity columns intact.
"""
from __future__ import annotations

from halcyon.constants import MATERIALS
from halcyon.contracts import ContractError
from .features import FEATURE_COLUMNS, FEATURE_VERSION, NUMERIC_FEATURES, validate_request


def build_spark_features(tables, cutoff: int, target_weeks: list[int], *, run_id, release_id, window_id):
    """Build Spark features from pinned raw table DataFrames.

    Pass one release's tables, or tables with a ``release_id`` column (filtered
    here). Demand and suppliers are known inputs. All other tables are filtered
    on publication/observation ``week <= cutoff`` before any transformation.
    Required history and target coverage are checked; no silent null imputation.
    Identity adds run_id/release_id/window_id to the pandas FEATURE_COLUMNS.
    """
    weeks = validate_request(cutoff, target_weeks)
    if any(not isinstance(value, str) or not value for value in (run_id, release_id, window_id)):
        raise ContractError("run_id, release_id and window_id must be nonempty strings")
    from pyspark.sql import Window, functions as F

    required = ("suppliers", "outcomes", "prices", "tariffs", "shipping", "macro", "supply_history", "demand")
    missing = set(required) - set(tables)
    if missing:
        raise ContractError(f"Spark features: missing tables {sorted(missing)}")
    source = {}
    for name in required:
        frame = tables[name]
        if "release_id" in frame.columns:
            frame = frame.filter(F.col("release_id") == release_id)
        # Strip persistence context before joins; the output context is supplied
        # explicitly by the caller, not inherited from possibly unrelated runs.
        context = [c for c in ("run_id", "release_id", "window_id", "feature_version", "cutoff_week") if c in frame.columns]
        frame = frame.drop(*context)
        source[name] = frame if name in ("suppliers", "demand") else frame.filter(F.col("week") <= cutoff)
    suppliers = source["suppliers"]
    session = suppliers.sparkSession
    targets = session.createDataFrame([(w,) for w in weeks], "target_week long")
    material_keys = session.createDataFrame([(m,) for m in MATERIALS], "material string")
    keys = targets.crossJoin(material_keys)

    def latest(frame, partition):
        order = Window.partitionBy(*partition).orderBy(F.col("week").desc())
        return frame.withColumn("_latest", F.row_number().over(order)).filter("_latest = 1").drop("_latest")

    def material_aggregate(frame, columns, count_name, count_column="week"):
        return frame.groupBy("material").agg(
            *[F.avg(c).alias(f"{c}_mean") for c in columns],
            F.count(count_column).alias(count_name),
        )

    def eligible(frame):
        return frame.join(suppliers.select("material", "country"), ["material", "country"], "inner")

    # Lag and rolling windows are evaluated only after filtering the observation
    # table; they never see realized data from a later training/forecast origin.
    chronological = Window.partitionBy("material").orderBy("week")
    history = source["outcomes"].withColumn(
        "benchmark_lag_1", F.coalesce(F.lag("benchmark_price", 1).over(chronological), F.first("benchmark_price").over(chronological))
    ).withColumn(
        "benchmark_lag_4", F.coalesce(F.lag("benchmark_price", 4).over(chronological), F.first("benchmark_price").over(chronological))
    )
    for n in (4, 13, 26):
        rolling = chronological.rangeBetween(1 - n, 0)
        history = history.withColumn(f"benchmark_mean_{n}", F.avg("benchmark_price").over(rolling)).withColumn(
            f"disruption_rate_{n}", F.avg("disrupted").over(rolling)
        )
    history = history.withColumn("benchmark_std_13", F.stddev_pop("benchmark_price").over(chronological.rangeBetween(-12, 0)))
    origin = latest(history, ["material"])
    # If outcomes are stale, cutoff-anchored rolling ranges differ from a window
    # ending at the last observation. Compute these explicitly for parity.
    aggregates = source["outcomes"].groupBy("material").agg(
        F.count("*").cast("double").alias("history_weeks"),
        F.avg("disrupted").alias("disruption_rate_all"),
        *[F.avg(F.when(F.col("week") > cutoff - n, F.col("benchmark_price"))).alias(f"_benchmark_mean_{n}") for n in (4, 13, 26)],
        *[F.avg(F.when(F.col("week") > cutoff - n, F.col("disrupted"))).alias(f"_disruption_rate_{n}") for n in (4, 13, 26)],
        F.stddev_pop(F.when(F.col("week") > cutoff - 13, F.col("benchmark_price"))).alias("_benchmark_std_13"),
    )
    origin = origin.join(aggregates, "material").select(
        "material", F.col("benchmark_price").alias("latest_benchmark_price"),
        "benchmark_lag_1", "benchmark_lag_4",
        *[F.when(F.col("week") == cutoff, F.col(f"benchmark_mean_{n}")).otherwise(F.col(f"_benchmark_mean_{n}")).alias(f"benchmark_mean_{n}") for n in (4, 13, 26)],
        *[F.when(F.col("week") == cutoff, F.col(f"disruption_rate_{n}")).otherwise(F.col(f"_disruption_rate_{n}")).alias(f"disruption_rate_{n}") for n in (4, 13, 26)],
        F.when(F.col("week") == cutoff, F.col("benchmark_std_13")).otherwise(F.col("_benchmark_std_13")).alias("benchmark_std_13"),
        (F.col("benchmark_price") / F.col("benchmark_lag_4") - 1).alias("benchmark_change_4"),
        F.col("disrupted").cast("double").alias("latest_disrupted"),
        "disruption_rate_all", "history_weeks", (F.lit(cutoff) - F.col("week")).cast("double").alias("outcome_age_weeks"),
    )
    price_history = eligible(source["prices"])
    prices = material_aggregate(latest(price_history, ["material", "country"]), ("spot_price", "futures_4w"), "_price_count")
    price_rolling = price_history.groupBy("material").agg(
        *[F.avg(F.when(F.col("week") > cutoff - n, F.col("spot_price"))).alias(f"spot_mean_{n}") for n in (4, 13)]
    )
    prices = prices.join(price_rolling, "material").withColumn("futures_spot_ratio", F.col("futures_4w_mean") / F.col("spot_price_mean"))
    tariff_history = eligible(source["tariffs"])
    current_tariff = latest(tariff_history, ["material", "country"]).select("material", "country", "tariff_rate")
    tariffs = material_aggregate(current_tariff, ("tariff_rate",), "_tariff_count", "country")
    country_targets = current_tariff.crossJoin(targets)
    announcements = tariff_history.filter(
        F.col("announced_rate").isNotNull()
        & (F.col("announced_effective_week") > cutoff)
    ).select("material", "country", F.col("week").alias("publication_week"), "announced_rate", "announced_effective_week")
    # A conditional join, rather than post-filtering, is essential: a country
    # whose only announcement takes effect later still needs its current tariff.
    a, b = country_targets.alias("a"), announcements.alias("b")
    announced = a.join(b, (F.col("a.material") == F.col("b.material")) & (F.col("a.country") == F.col("b.country")) & (F.col("b.announced_effective_week") <= F.col("a.target_week")), "left").select(
        "a.material", "a.country", "a.target_week", "a.tariff_rate", "b.publication_week", "b.announced_rate"
    )
    announced = announced.withColumn("_rank", F.row_number().over(Window.partitionBy("material", "country", "target_week").orderBy(F.col("publication_week").desc_nulls_last()))).filter("_rank = 1")
    target_tariffs = announced.groupBy("material", "target_week").agg(F.avg(F.coalesce("announced_rate", "tariff_rate")).alias("target_tariff_mean"))
    shipping = suppliers.select("material", "lane").join(latest(source["shipping"], ["lane"]), "lane", "left")
    shipping = material_aggregate(shipping, ("container_rate", "transit_days", "congestion_index"), "_shipping_count")
    macro = suppliers.select("material", "country").join(latest(source["macro"], ["country"]), "country", "left")
    macro = material_aggregate(macro, ("pmi", "fx_rate", "cpi_yoy", "policy_rate", "tension_index"), "_macro_count")
    static = suppliers.groupBy("material").agg(
        F.avg("base_lead_weeks").alias("base_lead_weeks_mean"), F.sum("normal_capacity_units").alias("normal_capacity_units_sum"),
        F.countDistinct("country").alias("_supplier_count"),
    )
    supply_history = eligible(source["supply_history"])
    supply = latest(supply_history, ["material", "country"]).groupBy("material").agg(
        F.sum("capacity_units").alias("capacity_units_sum"), F.avg("lead_time_weeks").alias("lead_time_weeks_mean"), F.avg("landed_cost").alias("landed_cost_mean"),
        F.countDistinct("country").alias("_supply_count"),
    )
    supply4 = supply_history.filter(F.col("week") > cutoff - 4)
    capacity4 = supply4.groupBy("material", "week").agg(F.sum("capacity_units").alias("capacity"))
    capacity4 = capacity4.groupBy("material").agg(F.avg("capacity").alias("capacity_mean_4"))
    lead4 = supply4.groupBy("material").agg(F.avg("lead_time_weeks").alias("lead_time_mean_4"))
    demand4 = source["demand"].filter(F.col("week").between(cutoff - 3, cutoff)).groupBy("material").agg(F.avg("demand_units").alias("demand_mean_4"))
    demand = source["demand"].select(F.col("week").alias("target_week"), "material", "demand_units")
    result = keys
    for frame in (origin, prices, tariffs, shipping, macro, static, supply, capacity4, lead4, demand4):
        result = result.join(frame, "material", "left")
    result = result.join(target_tariffs, ["material", "target_week"], "left").join(demand, ["material", "target_week"], "left")
    result = result.withColumn("capacity_ratio", F.col("capacity_units_sum") / F.col("normal_capacity_units_sum")).withColumn(
        "demand_ratio", F.when(F.col("demand_mean_4") > 0, F.col("demand_units") / F.col("demand_mean_4")).otherwise(F.lit(1.0))
    ).withColumn("tariff_announced_delta_mean", F.col("target_tariff_mean") - F.col("tariff_rate_mean"))
    result = result.withColumn("cutoff_week", F.lit(int(cutoff))).withColumn("horizon", F.col("target_week") - cutoff).withColumn("feature_version", F.lit(FEATURE_VERSION))
    for name, value in (("run_id", run_id), ("release_id", release_id), ("window_id", window_id)):
        result = result.withColumn(name, F.lit(value))
    invalid = F.lit(False)
    for name in NUMERIC_FEATURES:
        result = result.withColumn(name, F.col(name).cast("double"))
        invalid = invalid | F.col(name).isNull() | F.isnan(name) | (F.abs(F.col(name)) == float("inf"))
    invalid = invalid | (F.col("latest_benchmark_price") <= 0) | (F.col("spot_price_mean") <= 0) | (F.col("outcome_age_weeks") >= 4)
    for name in ("_price_count", "_tariff_count", "_shipping_count", "_macro_count", "_supply_count"):
        invalid = invalid | F.col(name).isNull() | (F.col(name) != F.col("_supplier_count"))
    invalid = invalid | (F.col("_supplier_count") != 3)
    summary = result.agg(F.count("*").alias("rows"), F.countDistinct(F.struct("target_week", "material")).alias("keys"), F.sum(F.when(invalid, 1).otherwise(0)).alias("invalid")).first()
    if summary.rows != len(weeks) * len(MATERIALS) or summary.keys != summary.rows or summary.invalid:
        raise ContractError("Spark features: incomplete/duplicate target coverage or missing/nonfinite observed history")
    return result.select("run_id", "release_id", "window_id", *FEATURE_COLUMNS)
