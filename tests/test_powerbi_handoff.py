"""Static checks for Power BI project/source artifacts (not Desktop integration tests)."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_power_query_sources_use_generated_pipeline_outputs_and_project_parameter():
    query_dir = ROOT / "powerbi" / "TelecomRetention" / "PowerQuery"
    expected = {
        "Customer_Profile.m": "CustomerReport.csv",
        "Holdout_Scores.m": "HoldoutScores.csv",
        "Model_Metrics.m": "ModelMetrics.csv",
        "Confusion_Matrix.m": "ConfusionMatrix.csv",
        "Retention_Scenario.m": "RetentionScenario.csv",
        "ROC_Curve.m": "ROCCurvePlot.csv",
        "Precision_Recall_Curve.m": "PrecisionRecallCurvePlot.csv",
        "Feature_Importance.m": "FeatureImportanceTop10.csv",
        "Recommendations.m": "Recommendations.csv",
    }
    for filename, output_name in expected.items():
        source = (query_dir / filename).read_text(encoding="utf-8")
        assert f'ProjectRoot & "/powerbi/data/{output_name}"' in source
        assert "Table.PromoteHeaders" in source
        assert "Table.TransformColumnTypes" in source


def test_dax_measures_reference_actual_table_names_and_holdout_provenance():
    dax = (ROOT / "powerbi" / "dax" / "retention_measures.dax").read_text(encoding="utf-8")
    model = (ROOT / "powerbi" / "TelecomRetention" / "TelecomRetention.SemanticModel" / "definition" / "tables" / "customer_profile.tmdl").read_text(encoding="utf-8")
    assert "'Customer Profile'[customerID]" in dax and "'Customer Profile'[Churn]" in dax
    assert "'Holdout Scores'[customerID]" in dax
    assert "'Model Metrics'[roc_auc]" in dax
    assert "'Retention Scenario'[gross_charges_over_assumed_months_hypothetical]" in dax
    assert "measure 'XGBoost ROC AUC'" in model
    assert "measure 'XGBoost Average Precision'" in model


def test_native_pbip_project_and_validation_limits_are_documented():
    project = ROOT / "powerbi" / "TelecomRetention" / "TelecomRetention.pbip"
    pages = ROOT / "powerbi" / "TelecomRetention" / "TelecomRetention.Report" / "definition" / "pages" / "pages.json"
    assert project.exists()
    assert len(json.loads(pages.read_text(encoding="utf-8"))["pageOrder"]) == 6
    guide = (ROOT / "powerbi" / "README.md").read_text(encoding="utf-8")
    assert ".pbip" in guide
    assert "Desktop" in guide
    assert "hypothetical" in guide.lower()
