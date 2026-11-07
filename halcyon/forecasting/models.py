"""Deterministic pooled direct-horizon forecasts with point-in-time training."""
from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import ExtraTreesClassifier, ExtraTreesRegressor
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import OneHotEncoder

from ..contracts import ContractError
from .baseline import HistoricalForecaster
from .features import FEATURE_VERSION, build_features, validate_request

_CONTEXT = {"target_week", "material", "cutoff_week", "feature_version"}
_OUTPUT = ["target_week", "material", "disruption_prob", "price_forecast", "model_id"]


class PooledForecaster:
    """Pool materials and horizons; regress log price relative to each origin.

    Every predict call refits on labels released by its cutoff. Inner origins are
    independently narrowed before feature construction. No holdout scores or
    automatic parameter selection enter this estimator.
    """

    model_id = "pooled_direct_extra_trees_v1"

    def __init__(self, *, min_history: int = 26, origin_stride: int = 4,
                 max_horizon: int = 26, min_training_rows: int = 100,
                 n_estimators: int = 96, min_samples_leaf: int = 8,
                 max_depth: int | None = 12, random_state: int = 10,
                 disruption_mode: str = "pooled") -> None:
        for name, value in (("min_history", min_history), ("origin_stride", origin_stride),
                            ("max_horizon", max_horizon), ("min_training_rows", min_training_rows),
                            ("n_estimators", n_estimators), ("min_samples_leaf", min_samples_leaf)):
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if max_depth is not None and (not isinstance(max_depth, int) or max_depth < 1):
            raise ValueError("max_depth must be None or a positive integer")
        if disruption_mode not in {"pooled", "historical"}:
            raise ValueError("disruption_mode must be pooled or historical")
        self.disruption_mode = disruption_mode
        if disruption_mode == "historical":
            self.model_id = "historical_risk_pooled_price_v1"
        self.config = dict(min_history=min_history, origin_stride=origin_stride,
                           max_horizon=max_horizon, min_training_rows=min_training_rows,
                           n_estimators=n_estimators, min_samples_leaf=min_samples_leaf,
                           max_depth=max_depth, random_state=random_state,
                           disruption_mode=disruption_mode)
        self.metadata_: dict = {}
        self.feature_columns_: list[str] = []
        self.training_features_ = pd.DataFrame()
        self.preprocessor_ = None
        self.price_model_ = None
        self.disruption_model_ = None
        self.baseline_ = HistoricalForecaster()

    def predict(self, data, cutoff: int, target_weeks: list[int]) -> pd.DataFrame:
        weeks = validate_request(cutoff, target_weeks)
        if max(weeks) - cutoff > self.config["max_horizon"]:
            raise ContractError("requested horizon exceeds configured max_horizon")
        visible = data.as_of(cutoff)
        self.preprocessor_ = self.price_model_ = self.disruption_model_ = None
        self.feature_columns_ = []
        self.training_features_ = pd.DataFrame(
            columns=["target_week", "material", "cutoff_week", "horizon", "feature_version"])
        self.metadata_ = {
            "model_id": self.model_id, "feature_version": FEATURE_VERSION,
            "config": self.config.copy(), "cutoff_week": int(cutoff),
            "price_target": "log(target_benchmark_price / latest_benchmark_price)",
            "fallback": None, "feature_columns": [], "training_rows": 0,
            "training_origin_bounds": None, "training_target_bounds": None,
            "class_distribution": {},
            "training_features_artifact": "training_features.csv",
        }
        labels = visible["outcomes"]
        first_week = int(labels["week"].min())
        first_origin = first_week + self.config["min_history"] - 1
        frames = []
        for origin in range(first_origin, cutoff, self.config["origin_stride"]):
            targets = list(range(origin + 1, min(cutoff, origin + self.config["max_horizon"]) + 1))
            # Do not rely on the feature builder to enforce the inner boundary.
            frame = build_features(visible.as_of(origin), origin, targets)
            frames.append(frame)
        if not frames:
            return self._fallback(visible, cutoff, weeks, "short_history")
        features = pd.concat(frames, ignore_index=True)
        training = features.merge(
            labels[["week", "material", "benchmark_price", "disrupted"]].rename(
                columns={"week": "target_week"}),
            on=["target_week", "material"], how="inner", validate="many_to_one")
        valid = (np.isfinite(training["benchmark_price"]) & (training["benchmark_price"] > 0)
                 & np.isfinite(training["latest_benchmark_price"])
                 & (training["latest_benchmark_price"] > 0)
                 & training["disrupted"].isin([0, 1]))
        training = training.loc[valid].copy()
        self.training_features_ = training.loc[:, features.columns].reset_index(drop=True)
        self.feature_columns_ = [name for name in features.columns if name not in _CONTEXT
                                 and pd.api.types.is_numeric_dtype(features[name])]
        if "horizon" not in self.feature_columns_:
            raise ContractError("build_features must supply numeric horizon")
        self.metadata_["feature_columns"] = self.feature_columns_.copy()
        self.metadata_["training_rows"] = len(training)
        self.metadata_["class_distribution"] = {
            str(int(key)): int(value) for key, value in training["disrupted"].value_counts().items()}
        if len(training):
            self.metadata_["training_origin_bounds"] = [int(training["cutoff_week"].min()),
                                                         int(training["cutoff_week"].max())]
            self.metadata_["training_target_bounds"] = [int(training["target_week"].min()),
                                                         int(training["target_week"].max())]
        if len(training) < self.config["min_training_rows"]:
            return self._fallback(visible, cutoff, weeks, "insufficient_training_rows")
        if self.disruption_mode == "pooled" and training["disrupted"].nunique() < 2:
            return self._fallback(visible, cutoff, weeks, "single_class")
        self.preprocessor_ = ColumnTransformer([
            ("numeric", SimpleImputer(strategy="median", keep_empty_features=True), self.feature_columns_),
            ("material", OneHotEncoder(handle_unknown="ignore", sparse_output=False), ["material"]),
        ], remainder="drop")
        x = self.preprocessor_.fit_transform(self._model_frame(training))
        parameters = {key: self.config[key] for key in
                      ("n_estimators", "min_samples_leaf", "max_depth", "random_state")}
        # Single-threaded trees avoid oversubscribing concurrent development folds.
        self.price_model_ = ExtraTreesRegressor(**parameters, n_jobs=1)
        relative_price = np.log(training["benchmark_price"]) - np.log(training["latest_benchmark_price"])
        self.price_model_.fit(x, relative_price.to_numpy())
        if self.disruption_mode == "pooled":
            self.disruption_model_ = ExtraTreesClassifier(**parameters, n_jobs=1)
            self.disruption_model_.fit(x, training["disrupted"].to_numpy(dtype=int))
        prediction_features = build_features(visible, cutoff, weeks)
        x_prediction = self.preprocessor_.transform(self._model_frame(prediction_features))
        result = prediction_features[["target_week", "material"]].copy()
        if self.disruption_mode == "pooled":
            class_index = list(self.disruption_model_.classes_).index(1)
            result["disruption_prob"] = np.clip(
                self.disruption_model_.predict_proba(x_prediction)[:, class_index], 0.0, 1.0)
        else:
            result["disruption_prob"] = result["material"].map(labels.groupby("material")["disrupted"].mean())
        log_price = (np.log(prediction_features["latest_benchmark_price"].to_numpy(dtype=float))
                     + self.price_model_.predict(x_prediction))
        # Bound in log space only at floating-point limits, not market-price limits.
        result["price_forecast"] = np.exp(np.clip(log_price, -700.0, 700.0))
        result["model_id"] = self.model_id
        return result[_OUTPUT].reset_index(drop=True)

    def _model_frame(self, features: pd.DataFrame) -> pd.DataFrame:
        return features[[*self.feature_columns_, "material"]].replace([np.inf, -np.inf], np.nan)

    def _fallback(self, data, cutoff: int, weeks: list[int], reason: str) -> pd.DataFrame:
        result = self.baseline_.predict(data, cutoff, weeks).copy()
        self.metadata_["fallback"] = {"reason": reason, "model_id": self.baseline_.model_id}
        result["model_id"] = f"{self.model_id}:fallback:{reason}"
        return result[_OUTPUT].reset_index(drop=True)

    def save_artifacts(self, directory: str | Path) -> None:
        """Persist the most recent fit, including explicit baseline fallback state."""
        if not self.metadata_:
            raise RuntimeError("predict must be called before saving artifacts")
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "metadata.json").write_text(json.dumps(self.metadata_, indent=2), encoding="utf-8")
        schema = {"feature_version": FEATURE_VERSION, "numeric": self.feature_columns_,
                  "categorical": ["material"], "context_excluded": sorted(_CONTEXT)}
        (directory / "features.json").write_text(json.dumps(schema, indent=2), encoding="utf-8")
        self.training_features_.to_csv(directory / "training_features.csv", index=False)
        with (directory / "model.pkl").open("wb") as stream:
            pickle.dump(self, stream, protocol=pickle.HIGHEST_PROTOCOL)
