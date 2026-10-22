"""Unit and authentic-source checks for the telecom analysis pipeline."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from PIL import Image

from src.analysis import (
    DATA_CSV,
    MODEL_ARTIFACT,
    OUT,
    DataQualityError,
    build_retention_scenario,
    business_aggregates,
    calculate_metrics,
    find_best_threshold,
    load_and_clean,
    prepare_features,
    validate_and_clean,
)
from src.inference import load_model_artifact, score_customers

ROOT = Path(__file__).resolve().parents[1]


def test_authentic_source_shape_and_unique_customer_keys():
    df, report = validate_and_clean(DATA_CSV)
    assert (len(df), len(report["columns"])) == (7043, 21)
    assert df["customerID"].nunique() == len(df)
    assert report["duplicate_customer_id_rows"] == 0
    assert report["sha256"] == json.loads((ROOT / "data/source_metadata.json").read_text())["sha256"]


def test_blank_total_charges_are_zero_tenure_non_churn_rows_only():
    df, report = validate_and_clean(DATA_CSV)
    assert report["blank_total_charges_count"] == 11
    assert report["blank_total_charges_tenure_zero_count"] == 11
    assert report["blank_total_charges_nonzero_tenure_count"] == 0
    assert report["missing_values_by_column"] == {"TotalCharges": 11}
    assert report["zero_tenure_churned_count"] == 0
    assert int(df["TotalCharges"].eq(0).sum()) >= 11
    assert report["row_accounting"] == {"raw": 7043, "cleaned": 7043, "dropped": 0}


@pytest.mark.parametrize("mutation, message", [
    ("duplicate", "duplicated"),
    ("invalid_category", "categorical values"),
    ("invalid_target", "categorical values"),
    ("blank_id", "identifiers"),
    ("blank_charge", "Blank TotalCharges"),
])
def test_unsafe_source_values_are_rejected(tmp_path, mutation, message):
    frame = pd.read_csv(DATA_CSV, dtype={"TotalCharges": "string"})
    if mutation == "duplicate":
        frame.loc[1, "customerID"] = frame.loc[0, "customerID"]
    elif mutation == "invalid_category":
        frame.loc[0, "Contract"] = "Monthly-ish"
    elif mutation == "invalid_target":
        frame.loc[0, "Churn"] = "Unknown"
    elif mutation == "blank_id":
        frame.loc[0, "customerID"] = "  "
    else:
        frame.loc[0, "TotalCharges"] = " "
    path = tmp_path / f"{mutation}.csv"
    frame.to_csv(path, index=False)
    with pytest.raises(DataQualityError, match=message):
        validate_and_clean(path)


def test_model_features_exclude_identifier_outcome_and_derived_target():
    df = load_and_clean()
    X, y, numeric, categorical, preprocessor = prepare_features(df)
    assert not {"customerID", "Churn", "Churn_Flag", "tenure_band"}.intersection(X.columns)
    assert len(X) == len(y) == 7043
    assert set(numeric).isdisjoint(categorical)
    assert len(numeric) > 0 and len(categorical) > 0
    assert not hasattr(preprocessor, "transformers_")  # no fitting on the full dataset during preparation


def test_threshold_is_deterministic_and_bounded_for_training_oof_scores():
    probabilities = np.array([0.05, 0.15, 0.25, 0.6, 0.8, 0.9])
    labels = np.array([0, 0, 1, 1, 0, 1])
    threshold = find_best_threshold(labels, probabilities)
    assert 0.05 <= threshold <= 0.95
    assert find_best_threshold(labels, probabilities) == threshold


def test_metrics_match_known_confusion_and_probability_scores():
    labels = np.array([0, 0, 1, 1])
    probabilities = np.array([0.1, 0.8, 0.7, 0.9])
    result = calculate_metrics(labels, probabilities, threshold=0.5)
    assert result["confusion_matrix"] == {"tn": 1, "fp": 1, "fn": 0, "tp": 2}
    assert result["precision"] == pytest.approx(2 / 3)
    assert result["recall"] == pytest.approx(1.0)
    assert result["evaluation_size"] == 4
    assert result["positive_prevalence"] == pytest.approx(0.5)
    assert result["brier_score"] == pytest.approx(0.1875)


def test_addon_adoption_uses_internet_customer_denominator():
    df = load_and_clean()
    _, adoption = business_aggregates(df)
    internet_rows = df.loc[df["InternetService"].ne("No")]
    assert int(adoption["customers"].sum()) == len(internet_rows)
    assert set(adoption["addon_count"]) == {0, 1, 2, 3, 4}
    assert int(internet_rows["InternetService"].eq("No").sum()) == 0
    assert int(adoption["churned"].sum()) == int(internet_rows["Churn_Flag"].sum())


def test_scenario_math_is_explicit_and_does_not_claim_effectiveness():
    df = load_and_clean()
    scenarios, assumptions = build_retention_scenario(df, (0.10,), 20.0, 3)
    row = scenarios.iloc[0]
    assert row["customers_retained_hypothetical"] == pytest.approx(row["historically_churned_observed"] * 0.10)
    assert row["campaign_cost_hypothetical"] == pytest.approx(row["segment_customers_observed"] * 20)
    assert "unmeasured" in row["interpretation"]
    assert assumptions["months_retained_assumed"] == 3


def test_final_pipeline_outputs_reconcile_with_authentic_data():
    metrics_path = OUT / "metrics.json"
    scores_path = OUT / "customer_risk_scores.csv"
    importance_path = OUT / "feature_importance_shap.csv"
    assert metrics_path.is_file() and scores_path.is_file() and importance_path.is_file()
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    scores = pd.read_csv(scores_path)
    importance = pd.read_csv(importance_path)
    df = load_and_clean()
    assert metrics["dataset_rows"] == len(df) == 7043
    assert metrics["observed_churn_count"] == int(df["Churn_Flag"].sum()) == 1869
    assert metrics["test_size"] == len(scores.loc[scores["data_split"].eq("test")])
    assert metrics["test_size"] == 1409
    assert scores["customerID"].nunique() == len(scores) == len(df)
    assert set(scores["data_split"]) == {"train_oof", "test"}
    assert scores["churn_probability"].between(0, 1).all()
    assert metrics["shap"]["status"] == "passed"
    assert importance["mean_abs_shap"].gt(0).any()
    assert MODEL_ARTIFACT.is_file()
    assert metrics["model_artifact"]["sha256"]


def test_serialized_model_scores_feature_only_rows_and_preserves_customer_alignment():
    raw = pd.read_csv(DATA_CSV, dtype={"customerID": "string"}).head(8).drop(columns="Churn")
    artifact = load_model_artifact(MODEL_ARTIFACT)
    scores = score_customers(raw, artifact)
    assert scores["customerID"].tolist() == raw["customerID"].astype(str).tolist()
    assert len(scores) == len(raw)
    assert scores["churn_probability"].between(0, 1).all()
    assert set(scores["data_split"]) == {"external_inference"}
    assert not {"Churn", "observed_churn"}.intersection(scores.columns)


def test_inference_rejects_outcomes_empty_input_and_schema_drift():
    raw = pd.read_csv(DATA_CSV, dtype={"customerID": "string"}).head(2).drop(columns="Churn")
    artifact = load_model_artifact(MODEL_ARTIFACT)
    with pytest.raises(ValueError, match="empty"):
        score_customers(raw.iloc[:0], artifact)
    with pytest.raises(ValueError, match="unsupported columns"):
        score_customers(raw.assign(Churn="No"), artifact)
    with pytest.raises(ValueError, match="missing features"):
        score_customers(raw.drop(columns="tenure"), artifact)
    with pytest.raises(ValueError, match="unique"):
        score_customers(pd.concat([raw.iloc[:1], raw.iloc[:1]], ignore_index=True), artifact)


def test_chart_outputs_exist_and_are_valid_pngs():
    expected = [
        "churn_distribution.png", "churn_by_contract.png", "churn_by_tenure.png",
        "churn_by_payment_method.png", "churn_by_internet_service.png", "churn_by_tech_support.png",
        "churn_by_monthly_charge.png",
        "monthly_charges_dist.png", "tenure_distribution.png", "tenure_vs_monthly_charges.png",
        "churn_contribution_segments.png", "missing_value_diagnostics.png", "addon_adoption_churn.png",
        "roc_pr_curves.png", "holdout_confusion_matrix.png", "model_comparison.png",
        "holdout_probability_by_outcome.png", "holdout_calibration.png", "holdout_risk_tiers.png",
        "training_oof_threshold_tradeoff.png", "shap_summary.png", "shap_bar.png", "shap_waterfall.png",
    ]
    for filename in expected:
        path = OUT / filename
        assert path.is_file() and path.stat().st_size > 0
        with Image.open(path) as image:
            assert image.format == "PNG"
            image.verify()


def test_holdout_metrics_have_training_selected_thresholds_and_uncertainty():
    metrics = json.loads((OUT / "metrics.json").read_text(encoding="utf-8"))
    assert "out-of-fold training" in metrics["threshold_selection"]
    assert set(metrics["test_metrics"]) == {"logistic_regression", "xgboost"}
    for result in metrics["test_metrics"].values():
        assert result["evaluation_size"] == metrics["test_size"]
        assert result["threshold_source"].startswith("five-fold out-of-fold training")
        assert len(result["roc_auc_bootstrap_95pct_ci"]) == 2
        low, high = result["roc_auc_bootstrap_95pct_ci"]
        assert 0 <= low <= high <= 1
