"""Build a reproducible PBIP report and TMDL model from powerbi/data CSVs.

Run after ``scripts/prepare_powerbi.py``. The generated project imports only
local, project-relative CSV files through a single ProjectRoot M parameter.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "powerbi" / "data"
PROJECT_DIR = ROOT / "powerbi" / "TelecomRetention"
REPORT_DIR = PROJECT_DIR / "TelecomRetention.Report"
MODEL_DIR = PROJECT_DIR / "TelecomRetention.SemanticModel"
MODEL_DEFINITION_DIR = MODEL_DIR / "definition"
TABLES_DIR = MODEL_DEFINITION_DIR / "tables"
PAGES_DIR = REPORT_DIR / "definition" / "pages"
THEME_SOURCE = ROOT / "powerbi" / "theme.json"

TABLE_FILES = [
    ("Customer Profile", "CustomerReport.csv"),
    ("Holdout Scores", "HoldoutScores.csv"),
    ("Model Metrics", "ModelMetrics.csv"),
    ("Confusion Matrix", "ConfusionMatrix.csv"),
    ("ROC Curve", "ROCCurvePlot.csv"),
    ("Precision Recall Curve", "PrecisionRecallCurvePlot.csv"),
    ("Feature Importance", "FeatureImportanceTop10.csv"),
    ("Retention Scenario", "RetentionScenario.csv"),
    ("Recommendations", "Recommendations.csv"),
]

INT_COLUMNS = {
    "SeniorCitizen", "tenure", "Churn_Flag", "tenure_band_order", "risk_tier_order", "predicted_churn",
    "evaluation_size", "positive_count", "customers", "step", "rank",
    "segment_customers_observed", "historically_churned_observed",
    "retained_months_assumption",
}

MEASURES: list[tuple[str, str, str, str, str]] = [
    ("Total Customers", "DISTINCTCOUNT('Customer Profile'[customerID])", "#,0", "Customer KPIs", "Unique customer IDs in the current customer profile filter context."),
    ("Churned Customers", "CALCULATE([Total Customers], 'Customer Profile'[Churn] = \"Yes\")", "#,0", "Customer KPIs", "Unique customers labeled churned in the source snapshot."),
    ("Retained Customers", "[Total Customers] - [Churned Customers]", "#,0", "Customer KPIs", "Unique customers labeled not churned in the source snapshot."),
    ("Observed Churn Rate", "DIVIDE([Churned Customers], [Total Customers])", "0.0%", "Customer KPIs", "Churned customers divided by customers after current customer filters."),
    ("Observed Retention Rate", "DIVIDE([Retained Customers], [Total Customers])", "0.0%", "Customer KPIs", "Retained customers divided by customers after current customer filters."),
    ("Average Tenure Months", "AVERAGE('Customer Profile'[tenure])", "0.0", "Customer KPIs", "Mean observed tenure in months for the filtered customer profile."),
    ("Average Monthly Charges", "AVERAGE('Customer Profile'[MonthlyCharges])", "0.00", "Customer KPIs", "Mean MonthlyCharges; the source does not specify a currency code."),
    ("Average Monthly Charges among Churned", "CALCULATE(AVERAGE('Customer Profile'[MonthlyCharges]), 'Customer Profile'[Churn] = \"Yes\")", "0.00", "Commercial Exposure", "Descriptive mean charge among rows labeled churned; not a realized loss."),
    ("Monthly Charges Associated with Churned Customers", "CALCULATE(SUM('Customer Profile'[MonthlyCharges]), 'Customer Profile'[Churn] = \"Yes\")", "#,0.00", "Commercial Exposure", "Sum of observed monthly charges for churn-labeled customers; not proven future revenue loss."),
    ("Churn Contribution to Filtered Total", "DIVIDE([Churned Customers], CALCULATE([Churned Customers], ALLSELECTED('Customer Profile'))) ", "0.0%", "Segment Analysis", "Segment churn count divided by total churn count under the outer report selection."),
    ("Holdout Test Customers", "DISTINCTCOUNT('Holdout Scores'[customerID])", "#,0", "Model Evaluation", "Unique customers in the fixed held-out test split."),
    ("Holdout Churned Customers", "CALCULATE([Holdout Test Customers], 'Holdout Scores'[Churn] = \"Yes\")", "#,0", "Model Evaluation", "Observed churn labels in the fixed test split."),
    ("Holdout Observed Churn Rate", "DIVIDE([Holdout Churned Customers], [Holdout Test Customers])", "0.0%", "Model Evaluation", "Observed churn prevalence in the fixed test split; not recalculated by the model."),
    ("Holdout High Risk Customers", "CALCULATE([Holdout Test Customers], 'Holdout Scores'[risk_tier] IN {\"High\", \"Critical\"})", "#,0", "Model Evaluation", "Held-out customers assigned High or Critical risk tiers by the existing scoring export."),
    ("Average Holdout Churn Probability", "AVERAGE('Holdout Scores'[churn_probability])", "0.0%", "Model Evaluation", "Mean predicted probability across the fixed held-out test split or selected risk tier."),
    ("Holdout Predicted Positive Customers", "CALCULATE([Holdout Test Customers], 'Holdout Scores'[predicted_churn] = 1)", "#,0", "Model Evaluation", "Held-out cases classified positive at the model's documented threshold."),
    ("XGBoost ROC AUC", "CALCULATE(MAX('Model Metrics'[roc_auc]), 'Model Metrics'[model] = \"xgboost\")", "0.000", "Model Evaluation", "Fixed test-set ROC-AUC from the authoritative model output."),
    ("XGBoost Average Precision", "CALCULATE(MAX('Model Metrics'[pr_auc_average_precision]), 'Model Metrics'[model] = \"xgboost\")", "0.000", "Model Evaluation", "Fixed test-set average precision from the authoritative model output."),
    ("XGBoost Precision", "CALCULATE(MAX('Model Metrics'[precision]), 'Model Metrics'[model] = \"xgboost\")", "0.0%", "Model Evaluation", "Fixed test-set precision at the threshold selected from training OOF predictions."),
    ("XGBoost Recall", "CALCULATE(MAX('Model Metrics'[recall]), 'Model Metrics'[model] = \"xgboost\")", "0.0%", "Model Evaluation", "Fixed test-set recall at the threshold selected from training OOF predictions."),
    ("XGBoost F1", "CALCULATE(MAX('Model Metrics'[f1]), 'Model Metrics'[model] = \"xgboost\")", "0.000", "Model Evaluation", "Fixed test-set F1 at the threshold selected from training OOF predictions."),
    ("XGBoost Accuracy", "CALCULATE(MAX('Model Metrics'[accuracy]), 'Model Metrics'[model] = \"xgboost\")", "0.0%", "Model Evaluation", "Fixed test-set accuracy; interpret alongside class balance and confusion matrix."),
    ("XGBoost Threshold", "CALCULATE(MAX('Model Metrics'[threshold]), 'Model Metrics'[model] = \"xgboost\")", "0.00", "Model Evaluation", "Classification threshold chosen from five-fold out-of-fold training predictions."),
    ("XGBoost Evaluation Size", "CALCULATE(MAX('Model Metrics'[evaluation_size]), 'Model Metrics'[model] = \"xgboost\")", "#,0", "Model Evaluation", "Number of cases in the fixed test evaluation."),
    ("ROC Curve True Positive Rate", "AVERAGE('ROC Curve'[y_value])", "0.0%", "Model Evaluation", "Empirical held-out true-positive rate at each false-positive-rate coordinate."),
    ("Precision Recall Curve Precision", "AVERAGE('Precision Recall Curve'[y_value])", "0.0%", "Model Evaluation", "Empirical held-out precision at each recall coordinate; repeated coordinates are collapsed for plotting."),
    ("Mean Absolute SHAP", "AVERAGE('Feature Importance'[mean_abs_shap])", "0.000", "Model Interpretation", "Mean absolute SHAP value from the fitted XGBoost booster, in raw-margin units."),
    ("Hypothetical Gross Charges", "SUM('Retention Scenario'[gross_charges_over_assumed_months_hypothetical])", "#,0.00", "Scenario Analysis", "Illustrative charge arithmetic under the CSV assumptions; not revenue, profit, savings, or measured retention."),
]


def read_headers(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return next(csv.reader(handle))


def stable_id(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]


def tmdl_id(value: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "telecom-retention:" + value))


def json_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def csv_m_types(headers: list[str]) -> list[tuple[str, str]]:
    result = []
    for column in headers:
        if column in INT_COLUMNS:
            m_type = "Int64.Type"
        elif column in {"MonthlyCharges", "TotalCharges", "churn_probability", "threshold", "roc_auc", "pr_auc_average_precision", "precision", "recall", "f1", "accuracy", "specificity", "brier_score", "positive_prevalence", "mean_abs_shap", "x_value", "y_value", "effectiveness_assumption", "historical_churn_rate_observed", "average_monthly_charges_observed", "gross_monthly_charges_retained_hypothetical", "gross_charges_over_assumed_months_hypothetical", "campaign_cost_hypothetical", "cost_per_contact_assumption", "customers_retained_hypothetical"}:
            m_type = "type number"
        else:
            m_type = "type text"
        result.append((column, m_type))
    return result


def m_quote(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def make_m_query(csv_name: str, headers: list[str]) -> str:
    typed = ",\n        ".join(f"{{{m_quote(column)}, {m_type}}}" for column, m_type in csv_m_types(headers))
    return (
        "let\n"
        f"    Source = Csv.Document(File.Contents(ProjectRoot & \"/powerbi/data/{csv_name}\"), [Delimiter=\",\", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),\n"
        "    PromotedHeaders = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),\n"
        f"    TypedColumns = Table.TransformColumnTypes(PromotedHeaders, {{{typed}}}, \"en-US\")\n"
        "in\n"
        "    TypedColumns"
    )


def tmdl_table(table_name: str, csv_name: str, headers: list[str], m_query: str) -> str:
    lines = [f"table '{table_name}'", f"\tlineageTag: {tmdl_id('table/' + table_name)}"]
    for column in headers:
        data_type = "int64" if column in INT_COLUMNS else "double" if dict(csv_m_types(headers))[column] == "type number" else "string"
        summarize = "none" if data_type == "string" else "average" if data_type == "double" else "sum"
        lines += [
            f"\tcolumn '{column}'",
            f"\t\tdataType: {data_type}",
            f"\t\tsourceColumn: {column}",
            f"\t\tsummarizeBy: {summarize}",
            f"\t\tlineageTag: {tmdl_id('column/' + table_name + '/' + column)}",
        ]
        if table_name == "Customer Profile" and column == "tenure_band":
            lines.append("\t\tsortByColumn: tenure_band_order")
        if table_name in {"Customer Profile", "Holdout Scores"} and column == "risk_tier":
            lines.append("\t\tsortByColumn: risk_tier_order")
        if column == "Churn_Flag":
            lines.append("\t\tfolder: Data Quality")
    if table_name == "Customer Profile":
        lines += ["", "\t// DAX measures are kept with the main customer table so the model has no artificial helper table."]
        for name, formula, format_string, folder, description in MEASURES:
            expression = " ".join(formula.split())
            lines += [
                f"\tmeasure '{name}' = {expression}",
                f"\t\tformatString: {format_string}",
                f"\t\tdisplayFolder: {folder}",
                f"\t\tdescription: {json.dumps(description, ensure_ascii=False)}",
            ]
    lines += [
        "",
        f"\tpartition '{table_name}' = m",
        "\t\tmode: import",
        "\t\tsource =",
    ]
    lines.extend("\t\t\t" + line for line in m_query.splitlines())
    return "\n".join(lines) + "\n"


def column_ref(table: str, column: str, display_name: str | None = None) -> dict[str, Any]:
    field: dict[str, Any] = {
        "Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": column}
    }
    projection = {"field": field, "queryRef": f"{table}.{column}", "nativeQueryRef": f"{table}.{column}"}
    if display_name:
        projection["displayName"] = display_name
    return projection


def measure_ref(table: str, measure: str, display_name: str | None = None) -> dict[str, Any]:
    field: dict[str, Any] = {
        "Measure": {"Expression": {"SourceRef": {"Entity": table}}, "Property": measure}
    }
    projection = {"field": field, "queryRef": f"{table}.{measure}", "nativeQueryRef": f"{table}.{measure}"}
    if display_name:
        projection["displayName"] = display_name
    return projection


def title_expression(text: str) -> dict[str, Any]:
    encoded = "'" + text.replace("'", "''") + "'"
    return {"expr": {"Literal": {"Value": encoded}}}


def visual_container(
    page_key: str,
    index: int,
    visual_type: str,
    title: str,
    x: int,
    y: int,
    width: int,
    height: int,
    roles: dict[str, list[dict[str, Any]]],
    sort_field: tuple[str, str] | None = None,
    sort_descending: bool = False,
) -> tuple[str, dict[str, Any]]:
    name = stable_id(f"{page_key}:{index}:{title}")
    query_state = {role: {"projections": fields} for role, fields in roles.items()}
    query: dict[str, Any] = {"queryState": query_state}
    if sort_field:
        sort_table, sort_column = sort_field
        query["sortDefinition"] = {
            "sort": [{"field": {"Column": {"Expression": {"SourceRef": {"Entity": sort_table}}, "Property": sort_column}}, "direction": "Descending" if sort_descending else "Ascending"}],
            "isDefaultSort": False,
        }
    data = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/1.0.0/schema.json",
        "name": name,
        "position": {"x": x, "y": y, "z": index, "height": height, "width": width, "tabOrder": index},
        "visual": {
            "visualType": visual_type,
            "query": query,
            **({"objects": {"data": [{"properties": {"mode": title_expression("Dropdown")}}]}} if visual_type == "slicer" else {}),
            "visualContainerObjects": {
                "title": [{"properties": {"show": {"expr": {"Literal": {"Value": "true"}}}, "text": title_expression(title)}}]
            },
        },
    }
    return name, data


def page_visuals(page_key: str, visuals: list[dict[str, Any]]) -> None:
    visuals_dir = PAGES_DIR / page_id(page_key) / "visuals"
    if visuals_dir.exists():
        for visual_folder in list(visuals_dir.iterdir()):
            if not visual_folder.is_dir() or not re.fullmatch(r"[0-9a-f]{20}", visual_folder.name):
                continue
            files = [path for path in visual_folder.rglob("*") if path.is_file()]
            directories = sorted((path for path in visual_folder.rglob("*") if path.is_dir()), key=lambda path: len(path.parts), reverse=True)
            if files and all(path.name == "visual.json" for path in files):
                for path in files:
                    path.unlink()
                for path in directories:
                    path.rmdir()
                visual_folder.rmdir()
    visuals_dir.mkdir(parents=True, exist_ok=True)
    for index, spec in enumerate(visuals):
        name, visual = visual_container(page_key, index, **spec)
        json_write(visuals_dir / name / "visual.json", visual)


def chart(
    visual_type: str,
    title: str,
    x: int,
    y: int,
    width: int,
    height: int,
    category: tuple[str, str, str] | None,
    value: tuple[str, str, str],
    series: tuple[str, str, str] | None = None,
    sort_field: tuple[str, str] | None = None,
    sort_descending: bool = False,
) -> dict[str, Any]:
    roles: dict[str, list[dict[str, Any]]] = {
        "Y": [measure_ref(value[0], value[1], value[2]) if value[0] == "Customer Profile" else column_ref(value[0], value[1], value[2])]
    }
    if category:
        roles["Category"] = [column_ref(*category)]
    if series:
        roles["Series"] = [column_ref(*series)]
    return {"visual_type": visual_type, "title": title, "x": x, "y": y, "width": width, "height": height, "roles": roles, "sort_field": sort_field, "sort_descending": sort_descending}


def table_visual(title: str, x: int, y: int, width: int, height: int, fields: list[tuple[str, str, str, bool]]) -> dict[str, Any]:
    projections = [measure_ref(table, name, label) if is_measure else column_ref(table, name, label) for table, name, label, is_measure in fields]
    return {"visual_type": "tableEx", "title": title, "x": x, "y": y, "width": width, "height": height, "roles": {"Values": projections}, "sort_field": None, "sort_descending": False}


def card_visual(title: str, x: int, y: int, width: int, height: int, measure: str) -> dict[str, Any]:
    return {"visual_type": "card", "title": title, "x": x, "y": y, "width": width, "height": height, "roles": {"Values": [measure_ref("Customer Profile", measure)]}, "sort_field": None, "sort_descending": False}


def slicer_visual(title: str, x: int, y: int, width: int, height: int, table: str, column: str) -> dict[str, Any]:
    return {"visual_type": "slicer", "title": title, "x": x, "y": y, "width": width, "height": height, "roles": {"Values": [column_ref(table, column)]}, "sort_field": None, "sort_descending": False}


def page_id(key: str) -> str:
    return "4042edc56d604303be11" if key == "executive" else stable_id("page:" + key)


def clear_only_generated_orphan_pages() -> None:
    """Remove visual-only folders emitted by the first scaffold iteration.

    A candidate must be a direct 20-hex child of pages/, have no page.json,
    and contain only visual.json files. That keeps the cleanup narrowly scoped.
    """
    if not PAGES_DIR.exists():
        return
    for folder in PAGES_DIR.iterdir():
        if not folder.is_dir() or not re.fullmatch(r"[0-9a-f]{20}", folder.name):
            continue
        if (folder / "page.json").exists():
            continue
        files = [path for path in folder.rglob("*") if path.is_file()]
        directories = sorted((path for path in folder.rglob("*") if path.is_dir()), key=lambda path: len(path.parts), reverse=True)
        if files and all(path.name == "visual.json" for path in files):
            for path in files:
                path.unlink()
            for path in directories:
                path.rmdir()
            folder.rmdir()


def write_pages() -> list[dict[str, str]]:
    pages = [
        {"key": "executive", "displayName": "Executive Overview"},
        {"key": "drivers", "displayName": "Understanding Churn Drivers"},
        {"key": "segments", "displayName": "Customer Segments & Exposure"},
        {"key": "retention", "displayName": "Retention Opportunities"},
        {"key": "performance", "displayName": "Model Performance & Reliability"},
        {"key": "action", "displayName": "Retention Action Plan"},
    ]
    PAGES_DIR.mkdir(parents=True, exist_ok=True)
    json_write(PAGES_DIR / "pages.json", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.1.0/schema.json",
        "pageOrder": [page_id(page["key"]) for page in pages],
        "activePageName": page_id("executive"),
    })
    for page in pages:
        key = page["key"]
        page_folder = PAGES_DIR / page_id(key)
        json_write(page_folder / "page.json", {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json",
            "name": page_id(key),
            "displayName": page["displayName"],
            "displayOption": "FitToPage",
            "height": 720,
            "width": 1280,
        })
    return pages


def write_report_visuals(pages: list[dict[str, str]]) -> None:
    cp = "Customer Profile"
    holdout = "Holdout Scores"
    rec = "Recommendations"
    visuals: dict[str, list[dict[str, Any]]] = {}

    executive: list[dict[str, Any]] = []
    for i, (title, field) in enumerate([
        ("Contract filter", "Contract"),
        ("Tenure band filter", "tenure_band"),
        ("Internet service filter", "InternetService"),
        ("Payment method filter", "PaymentMethod"),
    ]):
        executive.append(slicer_visual(title, 24 + i * 309, 8, 295, 76, cp, field))
    executive_cards = [
        ("Total Customers", "Total Customers"),
        ("Churned Customers", "Churned Customers"),
        ("Retained Customers", "Retained Customers"),
        ("Observed Churn Rate", "Observed Churn Rate"),
        ("Average Tenure (months)", "Average Tenure Months"),
        ("Churned monthly charges (source units)", "Monthly Charges Associated with Churned Customers"),
    ]
    for i, (title, measure) in enumerate(executive_cards):
        executive.append(card_visual(title, 24 + i * 205, 92, 193, 72, measure))
    executive += [
        chart("donutChart", "Customer outcome mix", 24, 174, 390, 180, (cp, "Churn", "Observed Outcome"), (cp, "Total Customers", "Customers")),
        chart("clusteredBarChart", "Observed churn rate by contract", 430, 174, 405, 180, (cp, "Contract", "Contract"), (cp, "Observed Churn Rate", "Observed Churn Rate")),
        chart("clusteredColumnChart", "Customer count by tenure band", 850, 174, 405, 180, (cp, "tenure_band", "Tenure Band"), (cp, "Total Customers", "Customers")),
        chart("clusteredColumnChart", "Observed churn rate by tenure band", 24, 363, 610, 181, (cp, "tenure_band", "Tenure Band"), (cp, "Observed Churn Rate", "Observed Churn Rate")),
        chart("clusteredBarChart", "Customer counts by internet service", 650, 363, 605, 181, (cp, "InternetService", "Internet Service"), (cp, "Total Customers", "Customers")),
        table_visual("Evidence to investigate", 24, 554, 1231, 154, [
            (rec, "finding", "Observed finding", False),
            (rec, "supporting_metric", "Observed evidence", False),
            (rec, "proposed_action", "Investigation", False),
        ]),
    ]
    visuals["executive"] = executive

    drivers = [
        chart("clusteredBarChart", "Observed churn rate by contract", 20, 12, 405, 215, (cp, "Contract", "Contract"), (cp, "Observed Churn Rate", "Churn Rate")),
        chart("clusteredBarChart", "Observed churn rate by tenure band", 438, 12, 405, 215, (cp, "tenure_band", "Tenure Band"), (cp, "Observed Churn Rate", "Churn Rate")),
        chart("clusteredBarChart", "Observed churn rate by payment method", 856, 12, 405, 215, (cp, "PaymentMethod", "Payment Method"), (cp, "Observed Churn Rate", "Churn Rate")),
        chart("clusteredBarChart", "Observed churn rate by internet service", 20, 244, 405, 215, (cp, "InternetService", "Internet Service"), (cp, "Observed Churn Rate", "Churn Rate")),
        chart("clusteredBarChart", "Observed churn rate by monthly charge band", 438, 244, 405, 215, (cp, "MonthlyChargeBand", "Monthly Charge Band"), (cp, "Observed Churn Rate", "Churn Rate")),
        chart("clusteredBarChart", "Observed churn rate by technical support", 856, 244, 405, 215, (cp, "TechSupport", "Tech Support"), (cp, "Observed Churn Rate", "Churn Rate")),
        table_visual("Evidence-backed hypotheses to investigate", 20, 476, 1241, 222, [
            (rec, "finding", "Observed finding", False),
            (rec, "supporting_metric", "Count and rate", False),
            (rec, "priority", "Priority", False),
            (rec, "validation_required", "Validation required", False),
        ]),
    ]
    visuals["drivers"] = drivers

    segments = [
        chart("clusteredColumnChart", "Customers by service combination", 20, 12, 405, 215, (cp, "ServiceCombination", "Phone / internet"), (cp, "Total Customers", "Customers")),
        chart("clusteredColumnChart", "Churned customers by monthly charge band", 438, 12, 405, 215, (cp, "MonthlyChargeBand", "Monthly Charge Band"), (cp, "Churned Customers", "Churned Customers")),
        chart("clusteredColumnChart", "Average monthly charges by churn outcome (source units)", 856, 12, 405, 215, (cp, "Churn", "Observed Outcome"), (cp, "Average Monthly Charges", "Average Charges")),
        chart("lineChart", "Average monthly charges by tenure band and churn outcome", 20, 244, 600, 225, (cp, "tenure_band", "Tenure Band"), (cp, "Average Monthly Charges", "Average Monthly Charges"), (cp, "Churn", "Observed Outcome")),
        table_visual("Customer summary by contract", 632, 244, 629, 225, [
            (cp, "Contract", "Contract", False),
            (cp, "Total Customers", "Customers", True),
            (cp, "Churned Customers", "Churned", True),
            (cp, "Observed Churn Rate", "Churn Rate", True),
            (cp, "Average Monthly Charges", "Avg. Charges", True),
        ]),
        table_visual("Commercial interpretation and follow-up", 20, 486, 1241, 212, [
            (rec, "finding", "Finding", False),
            (rec, "supporting_metric", "Evidence", False),
            (rec, "business_implication", "Business implication", False),
            (rec, "validation_required", "Next validation", False),
        ]),
    ]
    visuals["segments"] = segments

    retention = [
        chart("clusteredColumnChart", "Held-out test customers by risk tier", 20, 12, 405, 215, (holdout, "risk_tier", "Risk Tier"), (cp, "Holdout Test Customers", "Test Customers")),
        chart("clusteredColumnChart", "Observed test churn rate by risk tier", 438, 12, 405, 215, (holdout, "risk_tier", "Risk Tier"), (cp, "Holdout Observed Churn Rate", "Observed Churn Rate")),
        chart("clusteredColumnChart", "Average predicted probability by risk tier", 856, 12, 405, 215, (holdout, "risk_tier", "Risk Tier"), (cp, "Average Holdout Churn Probability", "Average Predicted Probability")),
        chart("clusteredBarChart", "High-risk test customers by contract", 20, 244, 600, 225, (holdout, "Contract", "Contract"), (cp, "Holdout High Risk Customers", "High-risk Test Customers")),
        chart("clusteredColumnChart", "Mean predicted probability by actual outcome", 632, 244, 629, 225, (holdout, "Churn", "Observed Outcome"), (cp, "Average Holdout Churn Probability", "Average Predicted Probability")),
        table_visual("Evidence for retention investigations", 20, 486, 1241, 212, [
            (rec, "finding", "Observed finding", False),
            (rec, "supporting_metric", "Evidence", False),
            (rec, "proposed_action", "Proposed investigation", False),
            (rec, "evidence_scope", "Scope and caveat", False),
        ]),
    ]
    visuals["retention"] = retention

    performance = [
        table_visual("Fixed holdout comparison", 20, 12, 1241, 145, [
            ("Model Metrics", "model", "Model", False),
            ("Model Metrics", "roc_auc", "ROC-AUC", False),
            ("Model Metrics", "pr_auc_average_precision", "Average Precision", False),
            ("Model Metrics", "precision", "Precision", False),
            ("Model Metrics", "recall", "Recall", False),
            ("Model Metrics", "f1", "F1", False),
            ("Model Metrics", "accuracy", "Accuracy", False),
            ("Model Metrics", "threshold", "Threshold", False),
            ("Model Metrics", "evaluation_size", "Test n", False),
        ]),
        table_visual("Confusion matrix counts at model threshold", 20, 170, 340, 216, [
            ("Confusion Matrix", "model", "Model", False),
            ("Confusion Matrix", "actual_outcome", "Actual", False),
            ("Confusion Matrix", "predicted_outcome", "Predicted", False),
            ("Confusion Matrix", "customers", "Customers", False),
        ]),
        chart("clusteredBarChart", "Top 10 mean absolute SHAP features (raw-margin units)", 375, 170, 430, 216, ("Feature Importance", "feature", "Feature"), ("Customer Profile", "Mean Absolute SHAP", "Mean Absolute SHAP"), sort_field=("Feature Importance", "mean_abs_shap"), sort_descending=True),
        chart("clusteredColumnChart", "Mean predicted probability by actual outcome", 820, 170, 441, 216, (holdout, "Churn", "Observed Outcome"), (cp, "Average Holdout Churn Probability", "Average Probability")),
        chart("lineChart", "ROC curve — held-out test scores", 20, 400, 600, 286, ("ROC Curve", "x_value", "False Positive Rate"), ("Customer Profile", "ROC Curve True Positive Rate", "True Positive Rate"), sort_field=("ROC Curve", "x_value")),
        chart("lineChart", "Precision–recall curve — held-out test scores", 632, 400, 629, 286, ("Precision Recall Curve", "x_value", "Recall"), ("Customer Profile", "Precision Recall Curve Precision", "Precision"), sort_field=("Precision Recall Curve", "x_value")),
    ]
    visuals["performance"] = performance

    action = [
        table_visual("Recommendations grounded in observed evidence", 20, 12, 1241, 390, [
            (rec, "finding", "Finding", False),
            (rec, "supporting_metric", "Supporting metric", False),
            (rec, "observed_segment", "Observed segment", False),
            (rec, "business_implication", "Business implication", False),
            (rec, "proposed_action", "Proposed action", False),
            (rec, "priority", "Priority", False),
            (rec, "validation_required", "Validation required", False),
        ]),
        table_visual("Illustrative scenario assumptions and arithmetic", 20, 416, 1241, 282, [
            ("Retention Scenario", "segment", "Scenario segment", False),
            ("Retention Scenario", "segment_customers_observed", "Observed customers", False),
            ("Retention Scenario", "historically_churned_observed", "Observed churned", False),
            ("Retention Scenario", "historical_churn_rate_observed", "Observed churn rate", False),
            ("Retention Scenario", "effectiveness_assumption", "Hypothetical effectiveness", False),
            ("Retention Scenario", "cost_per_contact_assumption", "Hypothetical cost / contact", False),
            ("Retention Scenario", "retained_months_assumption", "Assumed months", False),
            ("Retention Scenario", "customers_retained_hypothetical", "Hypothetical retained", False),
            ("Retention Scenario", "gross_charges_over_assumed_months_hypothetical", "Hypothetical gross charges", False),
            ("Retention Scenario", "interpretation", "Interpretation", False),
        ]),
    ]
    visuals["action"] = action

    for page in pages:
        page_visuals(page["key"], visuals[page["key"]])


def build_model(pages: list[dict[str, str]]) -> None:
    MODEL_DEFINITION_DIR.mkdir(parents=True, exist_ok=True)
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    power_query_dir = PROJECT_DIR / "PowerQuery"
    power_query_dir.mkdir(parents=True, exist_ok=True)
    table_refs = []
    dax_file = ROOT / "powerbi" / "dax" / "retention_measures.dax"
    dax_file.parent.mkdir(parents=True, exist_ok=True)
    dax_text = "\n\n".join(f"{name} =\n{formula}\n\n-- {description}" for name, formula, _, _, description in MEASURES)
    dax_file.write_text("# DAX measure library\n\n" + dax_text + "\n", encoding="utf-8")

    for table_name, csv_name in TABLE_FILES:
        csv_path = DATA_DIR / csv_name
        if not csv_path.exists():
            raise FileNotFoundError(f"Missing Power BI import table: {csv_path}. Run scripts/prepare_powerbi.py first.")
        headers = read_headers(csv_path)
        m_query = make_m_query(csv_name, headers)
        (power_query_dir / f"{re.sub(r'[^A-Za-z0-9]+', '_', table_name).strip('_')}.m").write_text(m_query + "\n", encoding="utf-8")
        (TABLES_DIR / f"{re.sub(r'[^A-Za-z0-9]+', '_', table_name).lower()}.tmdl").write_text(tmdl_table(table_name, csv_name, headers, m_query), encoding="utf-8")
        table_refs.append(table_name)

    project_root_m = m_quote(ROOT.as_posix())
    (MODEL_DEFINITION_DIR / "expressions.tmdl").write_text(
        "// Update this single local path after cloning the repository.\n"
        f"expression ProjectRoot = {project_root_m} meta [IsParameterQuery=true, Type=\"Text\", IsParameterQueryRequired=true]\n",
        encoding="utf-8",
    )
    (MODEL_DEFINITION_DIR / "database.tmdl").write_text(
        "database TelecomRetention\n\tcompatibilityLevel: 1702\n\tcompatibilityMode: powerBI\n",
        encoding="utf-8",
    )
    refs = "\n".join(f"\tref table '{name}'" for name in table_refs)
    (MODEL_DEFINITION_DIR / "model.tmdl").write_text(
        "model Model\n"
        "\tculture: en-US\n"
        "\tdefaultPowerBIDataSourceVersion: powerBI_V3\n"
        "\tsourceQueryCulture: en-US\n"
        "\tannotation PBI_QueryOrder = " + json.dumps(table_refs, ensure_ascii=False) + "\n"
        + refs + "\n",
        encoding="utf-8",
    )
    json_write(MODEL_DIR / "definition.pbism", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json",
        "version": "4.2",
        "settings": {"qnaEnabled": False},
    })
    json_write(MODEL_DIR / ".platform", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "SemanticModel", "displayName": "TelecomRetention.SemanticModel"},
        "config": {"version": "2.0", "logicalId": str(uuid.uuid5(uuid.NAMESPACE_URL, "telecom-retention-semantic-model"))},
    })


def build_project() -> None:
    if not (DATA_DIR / "CustomerReport.csv").exists():
        raise FileNotFoundError("Power BI input data is missing. Run scripts/prepare_powerbi.py first.")
    clear_only_generated_orphan_pages()
    pages = write_pages()
    build_model(pages)
    write_report_visuals(pages)

    # The report scaffold already contains this base theme and report schema.
    report_json_path = REPORT_DIR / "definition" / "report.json"
    report_json = json.loads(report_json_path.read_text(encoding="utf-8"))
    theme = json.loads(THEME_SOURCE.read_text(encoding="utf-8"))
    theme_name = "TelecomRetentionTheme-" + hashlib.sha256(THEME_SOURCE.read_bytes()).hexdigest()[:8] + ".json"
    theme["name"] = theme_name
    theme_path = REPORT_DIR / "StaticResources" / "RegisteredResources" / theme_name
    theme_path.parent.mkdir(parents=True, exist_ok=True)
    json_write(theme_path, theme)
    report_json["themeCollection"]["customTheme"] = {
        "name": theme_name,
        "reportVersionAtImport": {"visual": "2.11.0", "report": "3.4.0", "page": "2.3.1"},
        "type": "RegisteredResources",
    }
    report_json["resourcePackages"] = [
        item for item in report_json.get("resourcePackages", []) if item.get("name") != "RegisteredResources"
    ] + [{
        "name": "RegisteredResources",
        "type": "RegisteredResources",
        "items": [{"name": theme_name, "path": theme_name, "type": "CustomTheme"}],
    }]
    json_write(report_json_path, report_json)

    pbir_path = REPORT_DIR / "definition.pbir"
    pbir = json.loads(pbir_path.read_text(encoding="utf-8"))
    pbir["datasetReference"] = {"byPath": {"path": "../TelecomRetention.SemanticModel"}}
    json_write(pbir_path, pbir)
    pbip_path = PROJECT_DIR / "TelecomRetention.pbip"
    pbip = json.loads(pbip_path.read_text(encoding="utf-8")) if pbip_path.exists() else {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json",
        "version": "1.0",
        "settings": {"enableAutoRecovery": True},
    }
    # PBIP's artifact list contains the report; the semantic model is resolved
    # through the report's relative definition.pbir byPath reference.
    pbip["artifacts"] = [{"report": {"path": "TelecomRetention.Report"}}]
    json_write(pbip_path, pbip)

    page_guide = PROJECT_DIR / "REPORT_PAGES.md"
    page_guide.write_text(
        "# Report page definitions\n\n"
        "1. **Executive Overview** — source-snapshot KPIs, churn mix, contract/tenure patterns, customer counts and evidence-backed investigation priorities.\n"
        "2. **Understanding Churn Drivers** — observed rate comparisons by contract, tenure, payment, internet, charge band and support; these are associations, not causes.\n"
        "3. **Customer Segments & Exposure** — customer mix, observed charges grouped by churn status, phone/internet combinations, tenure/charge patterns and contract summary. Charges are source numeric units, not realized lost revenue.\n"
        "4. **Retention Opportunities** — risk tiers and outcome rates from the fixed held-out test split. It is retrospective evaluation, not a live customer campaign list.\n"
        "5. **Model Performance & Reliability** — fixed holdout model comparison, confusion counts, ROC/precision-recall plots from actual scores, predicted probabilities and top mean-absolute SHAP features. SHAP values are raw-margin associations, not causes.\n"
        "6. **Retention Action Plan** — evidence, investigation actions, validation needs and the explicitly hypothetical scenario arithmetic.\n\n"
        "All customer-profile measures recalculate with visual cross-filtering. Model evaluation tables and curve points are fixed outputs from the held-out split and are not recomputed by report filters.\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "pbip": str(pbip_path),
        "report": str(REPORT_DIR),
        "semantic_model": str(MODEL_DIR),
        "pages": [page["displayName"] for page in pages],
        "tables": [name for name, _ in TABLE_FILES],
        "visual_count": sum(len(list((PAGES_DIR / page_id(page["key"]) / "visuals").glob("*/visual.json"))) for page in pages),
        "project_root_parameter": ROOT.as_posix(),
    }, indent=2))


if __name__ == "__main__":
    build_project()
