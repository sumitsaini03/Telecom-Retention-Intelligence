"""Load the project-trained model and score new customer feature rows."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from src.analysis import MODEL_ARTIFACT


def load_model_artifact(path: Path = MODEL_ARTIFACT) -> dict[str, Any]:
    """Load and validate a local artifact created by ``src.analysis``.

    Joblib files can execute code when loaded. Only load artifacts created by
    this project or another trusted source.
    """
    if not path.is_file():
        raise FileNotFoundError(f"Model artifact not found: {path}. Run `python src/analysis.py` first.")
    artifact = joblib.load(path)
    required_keys = {
        "model", "model_identifier", "feature_columns", "numeric_columns",
        "categorical_columns", "threshold",
    }
    if not isinstance(artifact, dict) or not required_keys.issubset(artifact):
        raise ValueError(f"Model artifact is missing required metadata: {sorted(required_keys)}")
    features = artifact["feature_columns"]
    if not isinstance(features, list) or not features or len(features) != len(set(features)):
        raise ValueError("Model artifact has an invalid feature schema")
    if not hasattr(artifact["model"], "predict_proba"):
        raise ValueError("Model artifact does not contain a probability classifier")
    threshold = float(artifact["threshold"])
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("Model artifact threshold must be in [0, 1]")
    return artifact


def score_customers(customers: pd.DataFrame, artifact: dict[str, Any]) -> pd.DataFrame:
    """Score feature-only rows; reject targets, duplicate IDs, and schema drift."""
    if customers.empty:
        raise ValueError("Input customer table is empty")
    feature_columns = artifact["feature_columns"]
    missing = sorted(set(feature_columns) - set(customers.columns))
    unexpected = sorted(set(customers.columns) - set(feature_columns) - {"customerID"})
    if missing or unexpected:
        raise ValueError(f"Input schema mismatch; missing features={missing}, unsupported columns={unexpected}")

    if "customerID" in customers:
        identifiers = customers["customerID"].astype("string").str.strip()
        if identifiers.isna().any() or identifiers.eq("").any() or identifiers.duplicated().any():
            raise ValueError("customerID values must be present, non-empty, and unique")
    else:
        identifiers = pd.Series([f"input_row_{index + 1:06d}" for index in range(len(customers))], index=customers.index, dtype="string")

    features = customers.loc[:, feature_columns].copy()
    for column in artifact["numeric_columns"]:
        original = features[column]
        converted = pd.to_numeric(original, errors="coerce")
        if (original.notna() & converted.isna()).any():
            raise ValueError(f"Numeric feature {column!r} contains a non-numeric value")
        finite_values = converted.dropna().to_numpy(dtype=float)
        if not np.isfinite(finite_values).all():
            raise ValueError(f"Numeric feature {column!r} contains an infinite value")
        features[column] = converted

    for column in artifact["categorical_columns"]:
        features[column] = features[column].astype("object").replace({"": np.nan})

    probabilities = np.asarray(artifact["model"].predict_proba(features))[:, 1]
    if probabilities.shape != (len(customers),) or not np.isfinite(probabilities).all():
        raise ValueError("Model returned an invalid prediction shape or non-finite probabilities")
    if ((probabilities < 0) | (probabilities > 1)).any():
        raise ValueError("Model returned a probability outside [0, 1]")

    threshold = float(artifact["threshold"])
    risk_tier = np.select(
        [
            probabilities >= threshold + 0.15,
            probabilities >= threshold,
            probabilities >= max(0.0, threshold - 0.15),
        ],
        ["Critical", "High", "Medium"],
        default="Low",
    )
    return pd.DataFrame({
        "customerID": identifiers.astype(str).to_numpy(),
        "churn_probability": probabilities,
        "predicted_churn": (probabilities >= threshold).astype("int8"),
        "risk_tier": risk_tier,
        "model_identifier": artifact["model_identifier"],
        "data_split": "external_inference",
        "threshold": threshold,
    }, index=customers.index)
