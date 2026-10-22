"""Create validated Power BI import tables from the project pipeline outputs.

Run after ``python src/analysis.py``. This script does not retrain the model;
it joins the already generated customer and score exports and derives the
held-out XGBoost curves from the genuine test-score rows.
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score, roc_curve

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
POWERBI_DATA = ROOT / "powerbi" / "data"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str] | None = None) -> None:
    if columns is None:
        columns = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def churn_summary(rows: list[dict[str, str]], field: str, value: str, label: str) -> dict[str, Any]:
    selected = [row for row in rows if row[field] == value]
    churned = sum(row["Churn"] == "Yes" for row in selected)
    count = len(selected)
    return {
        "finding": label,
        "supporting_metric": f"{churned:,} churned / {count:,} customers ({churned / count:.1%})",
        "observed_segment": f"{field} = {value}",
        "business_implication": "This segment is a visible concentration for retention analysis; the snapshot does not identify the cause.",
        "proposed_action": "Investigate the associated customer journey and test any proposed change with a controlled pilot.",
        "priority": "High" if count >= 1000 and churned / count >= 0.35 else "Medium",
        "validation_required": "Check later-period data and run a controlled experiment before estimating intervention impact.",
        "evidence_scope": "Observed IBM Telco snapshot; descriptive association, not causation.",
    }


def main() -> None:
    customers = read_csv(OUTPUTS / "cleaned_customers.csv")
    scores = read_csv(OUTPUTS / "customer_risk_scores.csv")
    metrics = read_csv(OUTPUTS / "model_comparison.csv")
    matrix = read_csv(OUTPUTS / "confusion_matrix.csv")
    shap_rows = read_csv(OUTPUTS / "feature_importance_shap.csv")
    scenario = read_csv(OUTPUTS / "retention_scenario.csv")
    data_quality = json.loads((OUTPUTS / "data_quality_report.json").read_text(encoding="utf-8"))
    metric_json = json.loads((OUTPUTS / "metrics.json").read_text(encoding="utf-8"))

    customer_by_id = {row["customerID"]: row for row in customers}
    score_by_id = {row["customerID"]: row for row in scores}
    if len(customer_by_id) != len(customers) or len(score_by_id) != len(scores):
        raise ValueError("Customer IDs must be unique in both reporting inputs")
    if customer_by_id.keys() != score_by_id.keys():
        raise ValueError("Customer IDs in cleaned data and risk scores do not align exactly")
    if len(customers) != int(data_quality["clean_rows"]):
        raise ValueError("Clean customer count does not match the data-quality report")
    if any(not 0.0 <= float(score["churn_probability"]) <= 1.0 for score in scores):
        raise ValueError("Risk scores contain a probability outside [0, 1]")

    POWERBI_DATA.mkdir(parents=True, exist_ok=True)
    customer_rows: list[dict[str, Any]] = []
    for source in customers:
        score = score_by_id[source["customerID"]]
        monthly_charges = float(source["MonthlyCharges"])
        if monthly_charges < 30:
            charge_band = "0 to <30"
        elif monthly_charges < 60:
            charge_band = "30 to <60"
        elif monthly_charges < 90:
            charge_band = "60 to <90"
        else:
            charge_band = "90+"
        phone_label = "Phone" if source["PhoneService"] == "Yes" else "No phone"
        internet_label = "No internet" if source["InternetService"] == "No" else source["InternetService"]
        tenure_numbers = re.findall(r"\d+", source["tenure_band"])
        customer_rows.append({
            **source,
            "MonthlyChargeBand": charge_band,
            "ServiceCombination": f"{phone_label} / {internet_label}",
            "tenure_band_order": int(tenure_numbers[0]) if tenure_numbers else int(source["tenure"]),
            "risk_tier_order": {"Low": 1, "Medium": 2, "High": 3, "Critical": 4}.get(score["risk_tier"], 0),
            "churn_probability": score["churn_probability"],
            "predicted_churn": score["predicted_churn"],
            "risk_tier": score["risk_tier"],
            "model_identifier": score["model_identifier"],
            "data_split": score["data_split"],
        })
    write_csv(POWERBI_DATA / "CustomerReport.csv", customer_rows)

    # Preserve the authoritative model metrics and confusion-matrix output.
    write_csv(POWERBI_DATA / "ModelMetrics.csv", metrics)
    write_csv(POWERBI_DATA / "ConfusionMatrix.csv", matrix)
    write_csv(POWERBI_DATA / "FeatureImportance.csv", shap_rows)
    top_features = sorted(shap_rows, key=lambda row: float(row["mean_abs_shap"]), reverse=True)[:10]
    write_csv(POWERBI_DATA / "FeatureImportanceTop10.csv", [
        {"rank": rank, **row} for rank, row in enumerate(top_features, start=1)
    ])
    write_csv(POWERBI_DATA / "RetentionScenario.csv", scenario)

    # Curves are computed solely from genuine XGBoost test rows. Training OOF
    # values are deliberately excluded from held-out model evaluation charts.
    heldout = [row for row in customer_rows if row["data_split"] == "test"]
    y_true = [int(row["Churn_Flag"]) for row in heldout]
    y_score = [float(row["churn_probability"]) for row in heldout]
    if len(heldout) != int(metric_json["test_size"]):
        raise ValueError("Held-out score row count does not match metrics.json")
    expected = metric_json["test_metrics"]["xgboost"]
    calculated_auc = roc_auc_score(y_true, y_score)
    calculated_ap = average_precision_score(y_true, y_score)
    if abs(calculated_auc - float(expected["roc_auc"])) > 1e-10:
        raise ValueError("XGBoost ROC-AUC from reporting scores does not match metrics.json")
    if abs(calculated_ap - float(expected["pr_auc_average_precision"])) > 1e-10:
        raise ValueError("XGBoost average precision from reporting scores does not match metrics.json")

    roc_rows: list[dict[str, Any]] = []
    combined_curve_rows: list[dict[str, Any]] = []
    fpr, tpr, roc_thresholds = roc_curve(y_true, y_score)
    for step, (x_value, y_value, threshold) in enumerate(zip(fpr, tpr, roc_thresholds)):
        roc_rows.append({"model": "xgboost", "step": step, "x_value": x_value, "y_value": y_value, "threshold": threshold})
        combined_curve_rows.append({"model": "xgboost", "curve_type": "ROC", "step": step, "x_value": x_value, "y_value": y_value, "threshold": threshold})
    pr_rows: list[dict[str, Any]] = []
    precision, recall, pr_thresholds = precision_recall_curve(y_true, y_score)
    for step, (x_value, y_value) in enumerate(zip(recall, precision)):
        threshold = pr_thresholds[step] if step < len(pr_thresholds) else ""
        pr_rows.append({"model": "xgboost", "step": step, "x_value": x_value, "y_value": y_value, "threshold": threshold})
        combined_curve_rows.append({"model": "xgboost", "curve_type": "Precision-recall", "step": step, "x_value": x_value, "y_value": y_value, "threshold": threshold})
    write_csv(POWERBI_DATA / "CurvePoints.csv", combined_curve_rows)
    write_csv(POWERBI_DATA / "ROCCurve.csv", roc_rows)
    write_csv(POWERBI_DATA / "PrecisionRecallCurve.csv", pr_rows)
    # Preserve the exact threshold-level tables above. For the Power BI line
    # visuals, repeated x values are collapsed to the best y at that x so the
    # numeric axis plots the empirical curve without Power BI grouping duplicate
    # x categories. This is a display projection only; metrics use full scores.
    def unique_x_envelope(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        points: dict[float, dict[str, Any]] = {}
        for row in rows:
            x_value = float(row["x_value"])
            if x_value not in points or float(row["y_value"]) > float(points[x_value]["y_value"]):
                points[x_value] = row
        return [
            {"model": "xgboost", "step": step, "x_value": x_value, "y_value": points[x_value]["y_value"]}
            for step, x_value in enumerate(sorted(points))
        ]

    roc_plot_rows = unique_x_envelope(roc_rows)
    pr_plot_rows = unique_x_envelope(pr_rows)
    write_csv(POWERBI_DATA / "ROCCurvePlot.csv", roc_plot_rows)
    write_csv(POWERBI_DATA / "PrecisionRecallCurvePlot.csv", pr_plot_rows)
    write_csv(POWERBI_DATA / "HoldoutScores.csv", heldout, [
        "customerID", "Churn", "Churn_Flag", "tenure", "tenure_band", "tenure_band_order",
        "Contract", "InternetService", "PaymentMethod", "TechSupport", "MonthlyCharges",
        "MonthlyChargeBand", "ServiceCombination", "churn_probability", "predicted_churn", "risk_tier", "risk_tier_order",
        "model_identifier", "data_split",
    ])

    # Recommendations contain calculated evidence plus clearly labeled
    # hypotheses. They are not treatment effects or model output.
    recommendations = [
        churn_summary(customers, "Contract", "Month-to-month", "Month-to-month customers show elevated observed churn."),
        churn_summary(customers, "tenure_band", "0-12 months", "Customers in the first 12 months show elevated observed churn."),
        churn_summary(customers, "PaymentMethod", "Electronic check", "Electronic-check customers show elevated observed churn."),
        churn_summary(customers, "InternetService", "Fiber optic", "Fiber-optic customers show elevated observed churn."),
    ]
    write_csv(POWERBI_DATA / "Recommendations.csv", recommendations)

    # Independent reconciliations for the dashboard import layer.
    churned = sum(row["Churn"] == "Yes" for row in customers)
    retained = len(customers) - churned
    holdout_matrix: Counter[tuple[str, str]] = Counter()
    for row in matrix:
        if row["model"] == "xgboost":
            holdout_matrix[(row["actual_outcome"], row["predicted_outcome"])] += int(row["customers"])
    if sum(holdout_matrix.values()) != len(heldout):
        raise ValueError("XGBoost confusion-matrix cells do not sum to the held-out sample size")

    validation = {
        "status": "passed",
        "source_rows": int(data_quality["raw_rows"]),
        "customer_report_rows": len(customer_rows),
        "unique_customer_ids": len(customer_by_id),
        "joined_ids_match_exactly": True,
        "observed_churned": churned,
        "observed_retained": retained,
        "observed_churn_rate": churned / len(customers),
        "average_tenure_months": sum(int(row["tenure"]) for row in customers) / len(customers),
        "average_monthly_charges_source_units": sum(float(row["MonthlyCharges"]) for row in customers) / len(customers),
        "heldout_rows": len(heldout),
        "heldout_churned": sum(y_true),
        "heldout_probability_min": min(y_score),
        "heldout_probability_max": max(y_score),
        "roc_curve_points": len(roc_rows),
        "precision_recall_curve_points": len(pr_rows),
        "roc_curve_plot_points": len(roc_plot_rows),
        "precision_recall_curve_plot_points": len(pr_plot_rows),
        "xgboost_roc_auc_reconciled": calculated_auc,
        "xgboost_average_precision_reconciled": calculated_ap,
        "xgboost_confusion_matrix_total": sum(holdout_matrix.values()),
        "output_files": sorted(path.name for path in POWERBI_DATA.glob("*.csv")),
        "source_data_quality_sha256": data_quality["sha256"],
        "interpretation": "Power BI inputs are derived from the existing source, model-score, and evaluation outputs. Charges retain source numeric units; the source CSV does not define a currency code.",
    }
    (POWERBI_DATA / "validation.json").write_text(json.dumps(validation, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(validation, indent=2))


if __name__ == "__main__":
    main()
