"""Reproducible IBM Telco churn analysis and model pipeline.

Run from the repository root with ``python src/analysis.py``. The source CSV
is preserved; all cleaning and generated artifacts are written separately.
"""

from __future__ import annotations

import hashlib
import json
import platform
import warnings
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import joblib
import numpy as np
import pandas as pd
import shap
import sklearn
import xgboost
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import (
    GridSearchCV,
    StratifiedKFold,
    cross_val_predict,
    train_test_split,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from xgboost import XGBClassifier

warnings.filterwarnings("ignore", category=FutureWarning)

ROOT = Path(__file__).resolve().parents[1]
DATA_CSV = ROOT / "data" / "Telco-Customer-Churn.csv"
OUT = ROOT / "outputs"
MODEL_ARTIFACT = ROOT / "artifacts" / "xgboost_churn_model.joblib"
SOURCE_URL = "https://raw.githubusercontent.com/IBM/telco-customer-churn-on-icp4d/master/data/Telco-Customer-Churn.csv"
RANDOM_STATE = 42
TEST_SIZE = 0.20
TENURE_BANDS = ["0-12 months", "13-24 months", "25-48 months", "49-72 months"]
EXPECTED_COLUMNS = [
    "customerID", "gender", "SeniorCitizen", "Partner", "Dependents",
    "tenure", "PhoneService", "MultipleLines", "InternetService",
    "OnlineSecurity", "OnlineBackup", "DeviceProtection", "TechSupport",
    "StreamingTV", "StreamingMovies", "Contract", "PaperlessBilling",
    "PaymentMethod", "MonthlyCharges", "TotalCharges", "Churn",
]
CATEGORY_VALUES = {
    "gender": {"Female", "Male"},
    "SeniorCitizen": {0, 1},
    "Partner": {"Yes", "No"},
    "Dependents": {"Yes", "No"},
    "PhoneService": {"Yes", "No"},
    "MultipleLines": {"Yes", "No", "No phone service"},
    "InternetService": {"DSL", "Fiber optic", "No"},
    "OnlineSecurity": {"Yes", "No", "No internet service"},
    "OnlineBackup": {"Yes", "No", "No internet service"},
    "DeviceProtection": {"Yes", "No", "No internet service"},
    "TechSupport": {"Yes", "No", "No internet service"},
    "StreamingTV": {"Yes", "No", "No internet service"},
    "StreamingMovies": {"Yes", "No", "No internet service"},
    "Contract": {"Month-to-month", "One year", "Two year"},
    "PaperlessBilling": {"Yes", "No"},
    "PaymentMethod": {
        "Electronic check", "Mailed check", "Bank transfer (automatic)",
        "Credit card (automatic)",
    },
    "Churn": {"Yes", "No"},
}


class DataQualityError(ValueError):
    """Raised when source data cannot safely enter the analysis pipeline."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, default=str) + "\n", encoding="utf-8")


def _category_errors(df: pd.DataFrame) -> dict[str, list[str]]:
    errors: dict[str, list[str]] = {}
    for column, allowed in CATEGORY_VALUES.items():
        actual = set(df[column].dropna().unique().tolist())
        invalid = sorted(actual - allowed, key=str)
        if invalid:
            errors[column] = [str(value) for value in invalid]
    return errors


def validate_and_clean(path: Path = DATA_CSV) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Validate the raw IBM CSV, then return a separate cleaned frame and report."""
    if not path.is_file():
        raise FileNotFoundError(f"Source dataset not found: {path}")

    source_hash = _sha256(path)
    metadata_path = ROOT / "data" / "source_metadata.json"
    source_metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.is_file() else {}
    recorded_hash = source_metadata.get("sha256")
    if path.resolve() == DATA_CSV.resolve() and recorded_hash and recorded_hash.lower() != source_hash.lower():
        raise DataQualityError("Dataset SHA-256 differs from data/source_metadata.json; re-verify the source before analysis")

    raw = pd.read_csv(path, dtype={"customerID": "string", "TotalCharges": "string"})
    missing_columns = [name for name in EXPECTED_COLUMNS if name not in raw.columns]
    extra_columns = [name for name in raw.columns if name not in EXPECTED_COLUMNS]
    if missing_columns or extra_columns:
        raise DataQualityError(f"Unexpected dataset schema; missing={missing_columns}, extra={extra_columns}")
    raw = raw[EXPECTED_COLUMNS].copy()

    for column in ["SeniorCitizen", "tenure", "MonthlyCharges"]:
        raw[column] = pd.to_numeric(raw[column], errors="coerce")
    raw["TotalCharges"] = raw["TotalCharges"].astype("string").str.strip()
    blank_total_charges = raw["TotalCharges"].isna() | raw["TotalCharges"].eq("")
    total_charges = pd.to_numeric(raw["TotalCharges"].mask(blank_total_charges), errors="coerce")

    duplicate_id_count = int(raw["customerID"].duplicated(keep=False).sum())
    duplicate_row_count = int(raw.duplicated(keep=False).sum())
    missing_by_column = {key: int(value) for key, value in raw.isna().sum().items() if value}
    if blank_total_charges.any():
        missing_by_column["TotalCharges"] = int(blank_total_charges.sum())
    unexplained_missing = {key: value for key, value in missing_by_column.items() if key != "TotalCharges"}
    invalid_categories = _category_errors(raw)
    impossible: dict[str, int] = {
        "tenure_outside_0_72": int((~raw["tenure"].between(0, 72)).sum()),
        "senior_citizen_not_0_or_1": int((~raw["SeniorCitizen"].isin([0, 1])).sum()),
        "negative_monthly_charges": int((raw["MonthlyCharges"] < 0).sum()),
        "negative_total_charges": int((total_charges < 0).sum()),
        "non_numeric_total_charges": int((~blank_total_charges & total_charges.isna()).sum()),
    }
    zero_tenure = raw["tenure"].eq(0)
    blank_not_zero = int((blank_total_charges & ~zero_tenure).sum())
    zero_tenure_churned = int((zero_tenure & raw["Churn"].eq("Yes")).sum())

    fatal = []
    if raw["customerID"].isna().any() or raw["customerID"].str.strip().eq("").any() or duplicate_id_count:
        fatal.append("Customer identifiers are missing or duplicated")
    if unexplained_missing:
        fatal.append(f"Missing values are present outside the documented TotalCharges blanks: {unexplained_missing}")
    if invalid_categories:
        fatal.append("One or more categorical values are outside the documented source domain")
    if any(impossible.values()):
        fatal.append("One or more numeric values are impossible or could not be parsed")
    if blank_not_zero:
        fatal.append("Blank TotalCharges values exist for customers with non-zero tenure")
    if zero_tenure_churned:
        fatal.append("Zero-tenure churners make the blank-charge imputation unsupported")
    if fatal:
        raise DataQualityError("; ".join(fatal))

    clean = raw.copy()
    clean["TotalCharges"] = total_charges.fillna(0.0).astype(float)
    clean["SeniorCitizen"] = clean["SeniorCitizen"].astype("int64")
    clean["tenure"] = clean["tenure"].astype("int64")
    clean["MonthlyCharges"] = clean["MonthlyCharges"].astype(float)
    clean["Churn_Flag"] = clean["Churn"].eq("Yes").astype("int8")
    clean["tenure_band"] = pd.cut(
        clean["tenure"], bins=[-1, 12, 24, 48, 72], labels=TENURE_BANDS, ordered=True
    ).astype("string")
    if len(clean) != len(raw):
        raise DataQualityError("Rows were lost during cleaning")

    zero_charge_text = blank_total_charges & zero_tenure
    report = {
        "source_url": SOURCE_URL,
        "source_file": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
        "sha256": source_hash,
        "file_size_bytes": path.stat().st_size,
        "retrieval_date": source_metadata.get("retrieval_date"),
        "http_status": source_metadata.get("http_status"),
        "final_url": source_metadata.get("final_url"),
        "validation": "passed",
        "raw_rows": int(len(raw)),
        "clean_rows": int(len(clean)),
        "columns": list(raw.columns),
        "column_count": int(len(raw.columns)),
        "source_dtypes": {key: str(value) for key, value in raw.dtypes.items()},
        "unique_customer_ids": int(raw["customerID"].nunique(dropna=True)),
        "duplicate_customer_id_rows": duplicate_id_count,
        "duplicate_full_record_rows": duplicate_row_count,
        "missing_values_by_column": missing_by_column,
        "blank_total_charges_count": int(blank_total_charges.sum()),
        "blank_total_charges_tenure_zero_count": int(zero_charge_text.sum()),
        "blank_total_charges_nonzero_tenure_count": blank_not_zero,
        "zero_tenure_count": int(zero_tenure.sum()),
        "zero_tenure_churned_count": zero_tenure_churned,
        "total_charges_imputed_to_zero": int(zero_charge_text.sum()),
        "invalid_categories": invalid_categories,
        "impossible_numeric_values": impossible,
        "unexplained_missing_values": unexplained_missing,
        "churn_counts": {str(k): int(v) for k, v in raw["Churn"].value_counts(dropna=False).items()},
        "churn_rate": float(clean["Churn_Flag"].mean()),
        "reference_checks": {
            "expected_rows_7043": len(raw) == 7043,
            "expected_columns_21": len(raw.columns) == 21,
            "expected_churn_yes_1869": int(clean["Churn_Flag"].sum()) == 1869,
        },
        "numeric_summary": {
            "tenure_min": int(clean["tenure"].min()),
            "tenure_max": int(clean["tenure"].max()),
            "monthly_charges_min": float(clean["MonthlyCharges"].min()),
            "monthly_charges_max": float(clean["MonthlyCharges"].max()),
            "total_charges_min": float(clean["TotalCharges"].min()),
            "total_charges_max": float(clean["TotalCharges"].max()),
            "tenure_total_charges_correlation": float(clean[["tenure", "TotalCharges"]].corr().iloc[0, 1]),
            "rows_total_charges_below_monthly_charges": int(
                (clean["tenure"].ge(1) & clean["TotalCharges"].lt(clean["MonthlyCharges"])).sum()
            ),
            "zero_tenure_with_positive_monthly_charge": int(
                (clean["tenure"].eq(0) & clean["MonthlyCharges"].gt(0)).sum()
            ),
        },
        "row_accounting": {"raw": int(len(raw)), "cleaned": int(len(clean)), "dropped": int(len(raw) - len(clean))},
        "limitations": [
            "This is a single observational snapshot; churn associations do not establish causes.",
            "TotalCharges blanks are only imputed to zero after confirming all 11 have zero tenure and none churned.",
        ],
    }
    return clean, report


def load_and_clean(path: Path = DATA_CSV) -> pd.DataFrame:
    """Compatibility wrapper returning cleaned customer rows."""
    return validate_and_clean(path)[0]


def prepare_features(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, list[str], list[str], ColumnTransformer]:
    """Separate identifiers and outcomes from model features; return training-safe preprocessing."""
    excluded = {"customerID", "Churn", "Churn_Flag", "tenure_band"}
    feature_columns = [column for column in df.columns if column not in excluded]
    X = df[feature_columns].copy()
    y = df["Churn_Flag"].astype(int).copy()
    numeric = X.select_dtypes(include=["number"]).columns.tolist()
    categorical = [column for column in X.columns if column not in numeric]
    preprocessor = ColumnTransformer(
        transformers=[
            ("num", Pipeline([("imputer", SimpleImputer(strategy="median")), ("scale", StandardScaler())]), numeric),
            ("cat", Pipeline([
                ("imputer", SimpleImputer(strategy="most_frequent")),
                ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
            ]), categorical),
        ],
        remainder="drop",
        verbose_feature_names_out=False,
    )
    return X, y, numeric, categorical, preprocessor


def make_pipeline(preprocessor: ColumnTransformer, estimator: Any) -> Pipeline:
    return Pipeline([("preprocessor", preprocessor), ("classifier", estimator)])


def find_best_threshold(y_true: np.ndarray, probabilities: np.ndarray) -> float:
    """Choose the F1 threshold using only the supplied training OOF predictions."""
    candidates = np.unique(np.concatenate(([0.05, 0.5, 0.95], np.arange(0.05, 0.951, 0.01))))
    scores = [f1_score(y_true, probabilities >= threshold, zero_division=0) for threshold in candidates]
    best = max(scores)
    # On ties, favor the larger threshold, which avoids extra positive classifications.
    return float(candidates[np.flatnonzero(np.isclose(scores, best))[-1]])


def train_models(X: pd.DataFrame, y: pd.Series, preprocessor: ColumnTransformer) -> dict[str, Any]:
    """Tune both pipelines on the train partition; derive thresholds from train OOF scores."""
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, random_state=RANDOM_STATE, stratify=y
    )
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
    lr = make_pipeline(preprocessor, LogisticRegression(max_iter=2000, random_state=RANDOM_STATE))
    lr_search = GridSearchCV(lr, {"classifier__C": [0.25, 1.0, 4.0]}, scoring="roc_auc", cv=cv, n_jobs=1, refit=True)
    lr_search.fit(X_train, y_train)
    lr_model = lr_search.best_estimator_

    xgb = make_pipeline(preprocessor, XGBClassifier(
        objective="binary:logistic", eval_metric="logloss", tree_method="hist",
        random_state=RANDOM_STATE, n_jobs=1,
    ))
    xgb_search = GridSearchCV(
        xgb,
        {
            "classifier__n_estimators": [100, 200],
            "classifier__max_depth": [3, 4],
            "classifier__learning_rate": [0.05],
        },
        scoring="roc_auc", cv=cv, n_jobs=1, refit=True, error_score="raise",
    )
    xgb_search.fit(X_train, y_train)
    xgb_model = xgb_search.best_estimator_

    lr_oof = cross_val_predict(lr_model, X_train, y_train, cv=cv, method="predict_proba", n_jobs=1)[:, 1]
    xgb_oof = cross_val_predict(xgb_model, X_train, y_train, cv=cv, method="predict_proba", n_jobs=1)[:, 1]
    return {
        "lr_model": lr_model,
        "xgb_model": xgb_model,
        "lr_threshold": find_best_threshold(y_train.to_numpy(), lr_oof),
        "xgb_threshold": find_best_threshold(y_train.to_numpy(), xgb_oof),
        "lr_oof_proba": lr_oof,
        "xgb_oof_proba": xgb_oof,
        "lr_best_params": lr_search.best_params_,
        "xgb_best_params": xgb_search.best_params_,
        "lr_cv_roc_auc": float(lr_search.best_score_),
        "xgb_cv_roc_auc": float(xgb_search.best_score_),
        "X_train": X_train,
        "X_test": X_test,
        "y_train": y_train,
        "y_test": y_test,
        "cv_splits": 5,
    }


def _bootstrap_auc_interval(y_true: np.ndarray, probabilities: np.ndarray, seed: int = RANDOM_STATE) -> list[float]:
    rng = np.random.default_rng(seed)
    values: list[float] = []
    n = len(y_true)
    for _ in range(500):
        indices = rng.integers(0, n, n)
        if np.unique(y_true[indices]).size == 2:
            values.append(float(roc_auc_score(y_true[indices], probabilities[indices])))
    return [float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975))]


def calculate_metrics(y_true: np.ndarray, probabilities: np.ndarray, threshold: float) -> dict[str, Any]:
    predicted = (probabilities >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, predicted, labels=[0, 1]).ravel()
    metrics = {
        "threshold": float(threshold),
        "threshold_source": "five-fold out-of-fold training predictions; F1 objective",
        "roc_auc": float(roc_auc_score(y_true, probabilities)),
        "roc_auc_bootstrap_95pct_ci": _bootstrap_auc_interval(y_true, probabilities),
        "pr_auc_average_precision": float(average_precision_score(y_true, probabilities)),
        "precision": float(precision_score(y_true, predicted, zero_division=0)),
        "recall": float(recall_score(y_true, predicted, zero_division=0)),
        "f1": float(f1_score(y_true, predicted, zero_division=0)),
        "accuracy": float(accuracy_score(y_true, predicted)),
        "specificity": float(tn / (tn + fp)) if tn + fp else 0.0,
        "brier_score": float(brier_score_loss(y_true, probabilities)),
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        "evaluation_size": int(len(y_true)),
        "positive_count": int(np.sum(y_true)),
        "positive_prevalence": float(np.mean(y_true)),
    }
    return metrics


def evaluate(models: dict[str, Any]) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """Evaluate fitted models once on the untouched holdout and return probabilities."""
    y_test = models["y_test"].to_numpy()
    probabilities = {
        "logistic_regression": models["lr_model"].predict_proba(models["X_test"])[:, 1],
        "xgboost": models["xgb_model"].predict_proba(models["X_test"])[:, 1],
    }
    metrics = {
        "logistic_regression": calculate_metrics(y_test, probabilities["logistic_regression"], models["lr_threshold"]),
        "xgboost": calculate_metrics(y_test, probabilities["xgboost"], models["xgb_threshold"]),
    }
    return metrics, probabilities


def tenure_band(tenure: int) -> str:
    if tenure <= 12:
        return TENURE_BANDS[0]
    if tenure <= 24:
        return TENURE_BANDS[1]
    if tenure <= 48:
        return TENURE_BANDS[2]
    return TENURE_BANDS[3]


def business_aggregates(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return observed churn segment rates and add-on adoption among internet customers."""
    specs = {
        "Contract": "Contract",
        "tenure_band": "tenure_band",
        "InternetService": "InternetService",
        "PaymentMethod": "PaymentMethod",
        "SeniorCitizen": "senior_citizen",
        "PaperlessBilling": "PaperlessBilling",
        "TechSupport": "TechSupport",
        "OnlineSecurity": "OnlineSecurity",
        "monthly_charges_quartile": "monthly_charges_quartile",
    }
    work = df.copy()
    work["senior_citizen"] = np.where(work["SeniorCitizen"].eq(1), "Senior", "Non-senior")
    work["monthly_charges_quartile"] = pd.qcut(work["MonthlyCharges"], 4, labels=["Q1", "Q2", "Q3", "Q4"], duplicates="drop").astype("string")
    parts = []
    for field, dimension in specs.items():
        grouped = work.groupby(field, observed=False, dropna=False)["Churn_Flag"].agg(customers="size", churned="sum", churn_rate="mean").reset_index()
        grouped = grouped.rename(columns={field: "segment_value"})
        grouped.insert(0, "dimension", dimension)
        parts.append(grouped)
    aggregate = pd.concat(parts, ignore_index=True)
    aggregate["churn_rate_pct"] = aggregate["churn_rate"] * 100

    internet = work.loc[work["InternetService"].ne("No")].copy()
    addon_columns = ["OnlineSecurity", "OnlineBackup", "DeviceProtection", "TechSupport"]
    internet["addon_count"] = internet[addon_columns].eq("Yes").sum(axis=1)
    adoption = internet.groupby("addon_count")["Churn_Flag"].agg(customers="size", churned="sum", churn_rate="mean").reset_index()
    adoption.insert(0, "population", "Internet service customers only")
    adoption["churn_rate_pct"] = adoption["churn_rate"] * 100
    return aggregate, adoption


def run_eda(
    df: pd.DataFrame,
    aggregate: pd.DataFrame,
    adoption: pd.DataFrame,
    quality: dict[str, Any] | None = None,
) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    plt.style.use("seaborn-v0_8-whitegrid")
    navy, teal, red = "#17324d", "#248a8a", "#c94f52"

    def bar_rate(dimension: str, title: str, filename: str, horizontal: bool = False) -> None:
        data = aggregate.loc[aggregate["dimension"].eq(dimension)].sort_values("churn_rate")
        fig, ax = plt.subplots(figsize=(8, max(4, 0.4 * len(data))))
        if horizontal:
            bars = ax.barh(data["segment_value"].astype(str), data["churn_rate_pct"], color=teal)
            ax.set_xlabel("Observed churn rate (%)")
            for bar, row in zip(bars, data.itertuples()):
                ax.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height()/2,
                        f"{row.churn_rate_pct:.1f}%  ({row.churned:,}/{row.customers:,})", va="center", fontsize=8)
        else:
            bars = ax.bar(data["segment_value"].astype(str), data["churn_rate_pct"], color=navy)
            ax.set_ylabel("Observed churn rate (%)")
            ax.tick_params(axis="x", rotation=20)
            for bar, row in zip(bars, data.itertuples()):
                ax.text(bar.get_x()+bar.get_width()/2, bar.get_height()+0.5,
                        f"{row.churn_rate_pct:.1f}%\n{row.churned:,}/{row.customers:,}", ha="center", fontsize=8)
        ax.set_title(title, loc="left", fontweight="bold")
        fig.tight_layout()
        fig.savefig(OUT / filename, dpi=160, bbox_inches="tight")
        plt.close(fig)

    bar_rate("Contract", "Observed churn by contract", "churn_by_contract.png")
    bar_rate("tenure_band", "Observed churn by tenure", "churn_by_tenure.png")
    bar_rate("InternetService", "Observed churn by internet service", "churn_by_internet_service.png")
    bar_rate("PaymentMethod", "Observed churn by payment method", "churn_by_payment_method.png", horizontal=True)
    bar_rate("TechSupport", "Observed churn by technical support", "churn_by_tech_support.png", horizontal=True)
    bar_rate("monthly_charges_quartile", "Observed churn by monthly charge quartile", "churn_by_monthly_charge.png")

    fig, ax = plt.subplots(figsize=(7, 4))
    counts = df["Churn"].value_counts().reindex(["No", "Yes"])
    bars = ax.bar(["Retained", "Churned"], counts.values, color=[navy, red])
    for bar, count in zip(bars, counts.values):
        ax.text(bar.get_x()+bar.get_width()/2, bar.get_height()+30, f"{count:,}", ha="center")
    ax.set_title("Observed customer outcome", loc="left", fontweight="bold")
    ax.set_ylabel("Customers")
    fig.tight_layout()
    fig.savefig(OUT / "churn_distribution.png", dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 4))
    for label, color in [("No", navy), ("Yes", red)]:
        ax.hist(df.loc[df["Churn"].eq(label), "MonthlyCharges"], bins=30, alpha=0.55, label=label, color=color)
    ax.set(title="Monthly charges by observed churn label", xlabel="Monthly charges (source units; currency unspecified)", ylabel="Customers")
    ax.legend(title="Churn")
    fig.tight_layout()
    fig.savefig(OUT / "monthly_charges_dist.png", dpi=160, bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.hist(df["tenure"], bins=np.arange(-0.5, 73.5, 3), color=navy, edgecolor="white")
    ax.set(title="Customer tenure distribution", xlabel="Tenure (months)", ylabel="Customers")
    ax.set_xlim(-0.5, 72.5)
    fig.tight_layout()
    fig.savefig(OUT / "tenure_distribution.png", dpi=160, bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 5))
    for label, color in [("No", navy), ("Yes", red)]:
        group = df.loc[df["Churn"].eq(label)]
        ax.scatter(group["tenure"], group["MonthlyCharges"], s=14, alpha=0.35, label=label, color=color, linewidths=0)
    ax.set(
        title="Tenure and monthly charges by observed outcome",
        xlabel="Tenure (months)",
        ylabel="Monthly charges (source units; currency unspecified)",
    )
    ax.legend(title="Churn")
    fig.tight_layout()
    fig.savefig(OUT / "tenure_vs_monthly_charges.png", dpi=160, bbox_inches="tight")
    plt.close(fig)

    segment_columns = ["Contract", "InternetService", "PaymentMethod"]
    segment_summary = df.groupby(segment_columns, observed=True)["Churn_Flag"].agg(
        customers="size", churned="sum", churn_rate="mean"
    )
    segment_summary = segment_summary.loc[segment_summary["customers"].ge(50)].sort_values("churned").tail(10)
    segment_summary["segment"] = [" / ".join(map(str, values)) for values in segment_summary.index]
    fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.barh(segment_summary["segment"], segment_summary["churned"], color=teal)
    for bar, row in zip(bars, segment_summary.itertuples()):
        share = row.churned / max(1, int(df["Churn_Flag"].sum())) * 100
        ax.text(
            bar.get_width() + 5,
            bar.get_y() + bar.get_height() / 2,
            f"{row.churned:,} churn / {row.customers:,} ({row.churn_rate:.1%}); {share:.1f}% of churn",
            va="center",
            fontsize=8,
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.9, "pad": 1},
        )
    ax.set(
        title="Segments with the largest observed churn counts",
        xlabel="Customers labeled churned",
        ylabel="Contract / internet / payment",
    )
    ax.set_xlim(0, max(segment_summary["churned"]) * 1.8)
    ax.tick_params(axis="y", labelsize=9)
    ax.set_axisbelow(True)
    ax.grid(False, axis="y")
    ax.grid(axis="x", alpha=0.2, linestyle="--")
    fig.tight_layout()
    fig.savefig(OUT / "churn_contribution_segments.png", dpi=160, bbox_inches="tight")
    plt.close(fig)

    if quality is not None:
        missing = pd.Series(quality.get("missing_values_by_column", {}), dtype="int64").sort_values()
        fig, ax = plt.subplots(figsize=(8, max(3.2, 0.45 * max(1, len(missing)))))
        if missing.empty:
            ax.text(0.5, 0.5, "No raw missing values detected", ha="center", va="center", transform=ax.transAxes)
            ax.set_axis_off()
        else:
            bars = ax.barh(missing.index, missing.values, color=red)
            for bar, count in zip(bars, missing.values):
                ax.text(bar.get_width() + 0.1, bar.get_y() + bar.get_height() / 2, f"{count:,}", va="center")
            ax.set_xlabel("Raw missing entries")
            ax.set_xlim(0, max(missing.values) * 1.2)
        ax.set_title("Source data missing-value check", loc="left", fontweight="bold")
        fig.tight_layout()
        fig.savefig(OUT / "missing_value_diagnostics.png", dpi=160, bbox_inches="tight")
        plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(adoption["addon_count"], adoption["churn_rate_pct"], color=teal)
    ax.set(title="Add-on count and observed churn among internet customers", xlabel="Protective add-ons (0–4)", ylabel="Observed churn rate (%)")
    for x, row in adoption.iterrows():
        ax.text(row["addon_count"], row["churn_rate_pct"] + 0.7, f"{row['churn_rate_pct']:.1f}%\n(n={row['customers']:,})", ha="center", fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "addon_adoption_churn.png", dpi=160)
    plt.close(fig)


def explain_shap(model: Pipeline, X_test: pd.DataFrame, probabilities: np.ndarray) -> dict[str, Any]:
    """Explain the fitted XGBoost model using transformed feature names and TreeSHAP."""
    classifier = model.named_steps["classifier"]
    if hasattr(classifier, "get_booster"):
        booster = classifier.get_booster()
    elif hasattr(classifier, "_Booster") and classifier._Booster is not None:
        booster = classifier._Booster
    else:
        raise RuntimeError(f"Fitted XGBoost estimator has no accessible booster: {type(classifier).__name__}")
    preprocessor = model.named_steps["preprocessor"]
    sample = X_test.iloc[: min(500, len(X_test))]
    transformed = preprocessor.transform(sample)
    if hasattr(transformed, "toarray"):
        transformed = transformed.toarray()
    names = list(preprocessor.get_feature_names_out())
    transformed_frame = pd.DataFrame(transformed, columns=names, index=sample.index)
    explanation = shap.TreeExplainer(booster)(transformed_frame, check_additivity=False)
    values = np.asarray(explanation.values)
    if values.ndim == 3:
        values = values[:, :, -1]
        base_values = np.asarray(explanation.base_values)
        if base_values.ndim > 1:
            base_values = base_values[:, -1]
    else:
        base_values = np.asarray(explanation.base_values)
    if values.shape != transformed_frame.shape:
        raise RuntimeError(f"SHAP output shape {values.shape} does not match transformed features {transformed_frame.shape}")

    shap.summary_plot(values, transformed_frame, max_display=15, show=False)
    plt.title("XGBoost SHAP values (raw model output)", loc="left", fontweight="bold")
    plt.tight_layout()
    plt.savefig(OUT / "shap_summary.png", dpi=160, bbox_inches="tight")
    plt.close()
    shap.summary_plot(values, transformed_frame, plot_type="bar", max_display=15, show=False)
    plt.title("Mean absolute SHAP value", loc="left", fontweight="bold")
    plt.tight_layout()
    plt.savefig(OUT / "shap_bar.png", dpi=160, bbox_inches="tight")
    plt.close()

    highest_risk_idx = int(np.argmax(probabilities[: len(sample)]))
    local = shap.Explanation(
        values=values[highest_risk_idx],
        base_values=float(np.ravel(base_values)[highest_risk_idx] if np.ravel(base_values).size > 1 else np.ravel(base_values)[0]),
        data=transformed_frame.iloc[highest_risk_idx].to_numpy(),
        feature_names=names,
    )
    shap.plots.waterfall(local, max_display=12, show=False)
    plt.title("Local XGBoost explanation for highest-risk holdout row", loc="left", fontsize=10)
    plt.tight_layout()
    plt.savefig(OUT / "shap_waterfall.png", dpi=160, bbox_inches="tight")
    plt.close()

    importance = pd.DataFrame({"feature": names, "mean_abs_shap": np.abs(values).mean(axis=0)})
    importance = importance.sort_values("mean_abs_shap", ascending=False)
    importance.to_csv(OUT / "feature_importance_shap.csv", index=False)
    return {"status": "passed", "method": "TreeSHAP on fitted XGBoost Booster", "explained_holdout_rows": int(len(sample)), "transformed_feature_count": len(names), "top_features": importance.head(10).to_dict(orient="records"), "output_scale": "raw margin (log-odds)", "limitation": "Feature attributions describe fitted model associations, not causes."}


def plot_model_curves(
    models: dict[str, Any],
    metrics: dict[str, dict[str, Any]],
    probabilities: dict[str, np.ndarray],
) -> None:
    from sklearn.calibration import calibration_curve
    from sklearn.metrics import precision_recall_curve, roc_curve

    y_test = models["y_test"].to_numpy()
    model_specs = [
        ("logistic_regression", "Logistic regression", "#17324d"),
        ("xgboost", "XGBoost", "#c94f52"),
    ]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    axes[0].plot([0, 1], [0, 1], linestyle="--", color="#808b96", label="No-skill reference")
    for key, name, color in model_specs:
        false_positive_rate, true_positive_rate, _ = roc_curve(y_test, probabilities[key])
        precision, recall, _ = precision_recall_curve(y_test, probabilities[key])
        axes[0].plot(
            false_positive_rate, true_positive_rate, color=color, linewidth=2,
            label=f"{name} (AUC {metrics[key]['roc_auc']:.3f})",
        )
        axes[1].plot(
            recall, precision, color=color, linewidth=2,
            label=f"{name} (AP {metrics[key]['pr_auc_average_precision']:.3f})",
        )
    axes[1].axhline(float(np.mean(y_test)), linestyle="--", color="#808b96", label=f"Prevalence ({np.mean(y_test):.1%})")
    axes[0].set_title("ROC on untouched holdout", loc="left", fontweight="bold")
    axes[1].set_title("Precision–recall on untouched holdout", loc="left", fontweight="bold")
    axes[0].set(xlabel="False positive rate", ylabel="True positive rate", xlim=(0, 1), ylim=(0, 1))
    axes[1].set(xlabel="Recall", ylabel="Precision", xlim=(0, 1), ylim=(0, 1))
    for ax in axes:
        ax.legend(loc="lower right", frameon=False)
    fig.tight_layout()
    fig.savefig(OUT / "roc_pr_curves.png", dpi=160, bbox_inches="tight")
    plt.close(fig)

    xgb_metrics = metrics["xgboost"]
    matrix_values = xgb_metrics["confusion_matrix"]
    matrix = np.array([[matrix_values["tn"], matrix_values["fp"]], [matrix_values["fn"], matrix_values["tp"]]])
    fig, ax = plt.subplots(figsize=(6.5, 5.5))
    image = ax.imshow(matrix, cmap="Blues")
    ax.set_xticks([0, 1], labels=["No", "Yes"])
    ax.set_yticks([0, 1], labels=["No", "Yes"])
    ax.set(xlabel="Predicted churn", ylabel="Observed churn", title="XGBoost confusion matrix — holdout")
    for row in range(2):
        for column in range(2):
            ax.text(
                column, row, f"{matrix[row, column]:,}", ha="center", va="center",
                color="white" if matrix[row, column] > matrix.max() * 0.55 else "#17324d",
                fontsize=14, fontweight="bold",
            )
    fig.colorbar(image, ax=ax, label="Customers")
    fig.tight_layout()
    fig.savefig(OUT / "holdout_confusion_matrix.png", dpi=160, bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4.8))
    for label, color in [(0, "#17324d"), (1, "#c94f52")]:
        scores = probabilities["xgboost"][y_test == label]
        weights = np.full(len(scores), 100.0 / max(1, len(scores)))
        ax.hist(
            scores, bins=np.linspace(0, 1, 21), weights=weights, alpha=0.52, color=color,
            label=f"Observed {'churn' if label else 'retained'} (n={len(scores):,})",
        )
    threshold = float(xgb_metrics["threshold"])
    ax.axvline(threshold, linestyle="--", color="#111827", linewidth=1.5, label=f"Training OOF threshold ({threshold:.2f})")
    ax.set(
        title="XGBoost probability distribution — held-out customers",
        xlabel="Predicted churn probability",
        ylabel="Share within observed outcome (%)",
        xlim=(0, 1),
    )
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(OUT / "holdout_probability_by_outcome.png", dpi=160, bbox_inches="tight")
    plt.close(fig)

    metric_names = ["roc_auc", "pr_auc_average_precision", "accuracy", "precision", "recall", "f1"]
    metric_labels = ["ROC-AUC", "Average precision", "Accuracy", "Precision", "Recall", "F1"]
    x_positions = np.arange(len(metric_names))
    width = 0.36
    fig, ax = plt.subplots(figsize=(9, 5))
    for index, (key, name, color) in enumerate(model_specs):
        values = [metrics[key][metric] for metric in metric_names]
        ax.bar(x_positions + (index - 0.5) * width, values, width, label=name, color=color)
    ax.set_xticks(x_positions, labels=metric_labels, rotation=18, ha="right")
    ax.set(ylim=(0, 1), ylabel="Holdout score", title="Model metrics on the same untouched holdout")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(OUT / "model_comparison.png", dpi=160, bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 6))
    ax.plot([0, 1], [0, 1], linestyle="--", color="#808b96", label="Perfect calibration")
    for key, name, color in model_specs:
        fraction_positive, mean_probability = calibration_curve(
            y_test, probabilities[key], n_bins=10, strategy="quantile"
        )
        ax.plot(mean_probability, fraction_positive, marker="o", color=color, label=name)
    ax.set(
        xlabel="Mean predicted probability", ylabel="Observed churn fraction", xlim=(0, 1), ylim=(0, 1),
        title="Probability calibration — untouched holdout",
    )
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(OUT / "holdout_calibration.png", dpi=160, bbox_inches="tight")
    plt.close(fig)

    tiers = np.select(
        [
            probabilities["xgboost"] >= threshold + 0.15,
            probabilities["xgboost"] >= threshold,
            probabilities["xgboost"] >= max(0.0, threshold - 0.15),
        ],
        ["Critical", "High", "Medium"],
        default="Low",
    )
    tier_order = ["Low", "Medium", "High", "Critical"]
    tier_counts = pd.crosstab(y_test, pd.Categorical(tiers, categories=tier_order), normalize="index") * 100
    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    for index, (label, color) in enumerate([(0, "#17324d"), (1, "#c94f52")]):
        values = tier_counts.loc[label].reindex(tier_order, fill_value=0).to_numpy()
        ax.bar(
            np.arange(4) + (index - 0.5) * width, values, width, color=color,
            label=f"Observed {'churn' if label else 'retained'} (n={(y_test == label).sum():,})",
        )
    ax.set_xticks(np.arange(4), tier_order)
    ax.set(ylabel="Share within observed outcome (%)", title="Holdout risk-tier distribution by observed outcome")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(OUT / "holdout_risk_tiers.png", dpi=160, bbox_inches="tight")
    plt.close(fig)

    thresholds = np.unique(np.concatenate(([0.05, 0.5, 0.95], np.arange(0.05, 0.951, 0.01))))
    oof_y = models["y_train"].to_numpy()
    oof_probabilities = models["xgb_oof_proba"]
    precision_values, recall_values, f1_values = [], [], []
    for candidate in thresholds:
        predictions = oof_probabilities >= candidate
        precision_values.append(precision_score(oof_y, predictions, zero_division=0))
        recall_values.append(recall_score(oof_y, predictions, zero_division=0))
        f1_values.append(f1_score(oof_y, predictions, zero_division=0))
    fig, ax = plt.subplots(figsize=(8, 4.8))
    ax.plot(thresholds, precision_values, label="Precision", color="#17324d")
    ax.plot(thresholds, recall_values, label="Recall", color="#248a8a")
    ax.plot(thresholds, f1_values, label="F1", color="#c94f52", linewidth=2)
    ax.axvline(
        float(models["xgb_threshold"]), linestyle="--", color="#111827",
        label=f"Selected from training OOF ({models['xgb_threshold']:.2f})",
    )
    ax.set(
        xlabel="Probability threshold", ylabel="Training OOF score", xlim=(0.05, 0.95), ylim=(0, 1),
        title="XGBoost threshold trade-off — training OOF only",
    )
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(OUT / "training_oof_threshold_tradeoff.png", dpi=160, bbox_inches="tight")
    plt.close(fig)


def build_risk_scores(df: pd.DataFrame, models: dict[str, Any]) -> pd.DataFrame:
    scores = pd.DataFrame({
        "customerID": df["customerID"].astype(str),
        "observed_churn": df["Churn"].astype(str),
        "churn_probability": np.nan,
        "predicted_churn": pd.Series(pd.NA, index=df.index, dtype="Int64"),
        "risk_tier": pd.Series(index=df.index, dtype="string"),
        "model_identifier": "xgboost_gridsearch_v1",
        "data_split": pd.Series(index=df.index, dtype="string"),
    })
    train_index = models["X_train"].index
    test_index = models["X_test"].index
    threshold = models["xgb_threshold"]
    scores.loc[train_index, "churn_probability"] = models["xgb_oof_proba"]
    scores.loc[train_index, "data_split"] = "train_oof"
    scores.loc[test_index, "churn_probability"] = models["xgb_model"].predict_proba(models["X_test"])[:, 1]
    scores.loc[test_index, "data_split"] = "test"
    scores["predicted_churn"] = (scores["churn_probability"] >= threshold).astype("Int64")
    scores["risk_tier"] = pd.cut(
        scores["churn_probability"], bins=[-np.inf, max(0.0, threshold - 0.15), threshold, np.inf],
        labels=["Low", "Medium", "High"], right=False, include_lowest=True,
    ).astype("string")
    scores.loc[scores["churn_probability"] >= threshold + 0.15, "risk_tier"] = "Critical"
    if scores["customerID"].duplicated().any() or scores["churn_probability"].isna().any() or scores["data_split"].isna().any():
        raise DataQualityError("Risk-score output is incomplete or has duplicate customer IDs")
    return scores


def build_retention_scenario(
    df: pd.DataFrame,
    effectiveness_levels: tuple[float, ...] = (0.05, 0.10, 0.15),
    cost_per_customer: float = 50.0,
    months_retained: int = 6,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Create explicitly hypothetical scenario arithmetic; no causal effects are estimated."""
    if any(not 0 <= value <= 1 for value in effectiveness_levels) or cost_per_customer < 0 or months_retained < 0:
        raise ValueError("Scenario assumptions must be non-negative and effectiveness must be in [0, 1]")
    group_columns = ["Contract", "InternetService", "PaymentMethod"]
    stats = df.groupby(group_columns, observed=True).agg(
        customers=("Churn_Flag", "size"), churned=("Churn_Flag", "sum"), avg_monthly_charges=("MonthlyCharges", "mean")
    ).reset_index()
    stats = stats.loc[stats["customers"].ge(50)].copy()
    stats["churned_monthly_charges"] = stats["churned"] * stats["avg_monthly_charges"]
    top = stats.sort_values(["churned_monthly_charges", "customers"], ascending=False).iloc[0]
    segment = " | ".join(str(top[column]) for column in group_columns)
    rows = []
    for effect in effectiveness_levels:
        hypothetical_retained = float(top["churned"] * effect)
        rows.append({
            "segment": segment,
            "segment_customers_observed": int(top["customers"]),
            "historically_churned_observed": int(top["churned"]),
            "historical_churn_rate_observed": float(top["churned"] / top["customers"]),
            "average_monthly_charges_observed": float(top["avg_monthly_charges"]),
            "effectiveness_assumption": float(effect),
            "customers_retained_hypothetical": hypothetical_retained,
            "gross_monthly_charges_retained_hypothetical": hypothetical_retained * float(top["avg_monthly_charges"]),
            "gross_charges_over_assumed_months_hypothetical": hypothetical_retained * float(top["avg_monthly_charges"]) * months_retained,
            "campaign_cost_hypothetical": float(top["customers"] * cost_per_customer),
            "cost_per_contact_assumption": float(cost_per_customer),
            "retained_months_assumption": int(months_retained),
            "interpretation": "Arithmetic illustration only; intervention effectiveness and causal impact are unmeasured.",
        })
    assumptions = {
        "effectiveness_levels": list(effectiveness_levels),
        "cost_per_customer_assumed": cost_per_customer,
        "months_retained_assumed": months_retained,
        "segment_selection": "Highest observed churned monthly charges among Contract x InternetService x PaymentMethod segments with at least 50 customers.",
        "limitations": "Gross charges are not profit or savings. A randomized retention experiment and margin/cost data are needed to estimate campaign impact.",
    }
    return pd.DataFrame(rows), assumptions


def write_data_quality(report: dict[str, Any], clean: pd.DataFrame) -> None:
    _write_json(OUT / "data_quality_report.json", report)
    rows = [{"check": key, "result": json.dumps(value, default=str)} for key, value in report.items()]
    pd.DataFrame(rows).to_csv(OUT / "data_quality_report.csv", index=False)
    clean.to_csv(OUT / "cleaned_customers.csv", index=False)


def save_model_artifact(
    models: dict[str, Any],
    numeric_columns: list[str],
    categorical_columns: list[str],
    source_hash: str,
) -> dict[str, Any]:
    """Persist the train-fitted XGBoost pipeline and the schema needed for scoring."""
    MODEL_ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    artifact = {
        "model": models["xgb_model"],
        "model_identifier": "xgboost_gridsearch_v1",
        "feature_columns": list(models["X_train"].columns),
        "numeric_columns": list(numeric_columns),
        "categorical_columns": list(categorical_columns),
        "threshold": float(models["xgb_threshold"]),
        "threshold_source": "five-fold out-of-fold training predictions; F1 objective",
        "training_size": int(len(models["y_train"])),
        "source_sha256": source_hash,
        "python_version": platform.python_version(),
        "xgboost_version": xgboost.__version__,
        "scikit_learn_version": sklearn.__version__,
    }
    joblib.dump(artifact, MODEL_ARTIFACT, compress=3)
    metadata = {
        "artifact_path": str(MODEL_ARTIFACT.relative_to(ROOT)),
        "sha256": _sha256(MODEL_ARTIFACT),
        "model_identifier": artifact["model_identifier"],
        "feature_count": len(artifact["feature_columns"]),
        "training_size": artifact["training_size"],
        "threshold": artifact["threshold"],
        "threshold_source": artifact["threshold_source"],
        "source_sha256": source_hash,
        "limitations": "The saved estimator is trained on the 80% training partition. Its threshold is selected from training OOF predictions. It is a local prototype, not a validated production model.",
    }
    _write_json(OUT / "model_artifact_metadata.json", metadata)
    return metadata


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    clean, quality = validate_and_clean()
    write_data_quality(quality, clean)
    aggregate, adoption = business_aggregates(clean)
    aggregate.to_csv(OUT / "business_aggregates.csv", index=False)
    adoption.to_csv(OUT / "addon_adoption.csv", index=False)
    run_eda(clean, aggregate, adoption, quality)

    X, y, numeric_columns, categorical_columns, preprocessor = prepare_features(clean)
    models = train_models(X, y, preprocessor)
    metrics, holdout_probabilities = evaluate(models)
    artifact_metadata = save_model_artifact(models, numeric_columns, categorical_columns, quality["sha256"])
    plot_model_curves(models, metrics, holdout_probabilities)
    shap_status = explain_shap(models["xgb_model"], models["X_test"], holdout_probabilities["xgboost"])
    scores = build_risk_scores(clean, models)
    scores.to_csv(OUT / "customer_risk_scores.csv", index=False)
    scenario, assumptions = build_retention_scenario(clean)
    scenario.to_csv(OUT / "retention_scenario.csv", index=False)
    _write_json(OUT / "retention_scenario_inputs.json", assumptions)

    comparison_rows = []
    confusion_rows = []
    for model_name, result in metrics.items():
        comparison_rows.append({"model": model_name, **{key: value for key, value in result.items() if key != "confusion_matrix" and key != "roc_auc_bootstrap_95pct_ci"}})
        matrix = result["confusion_matrix"]
        confusion_rows.extend([
            {"model": model_name, "actual_outcome": "No", "predicted_outcome": "No", "customers": matrix["tn"]},
            {"model": model_name, "actual_outcome": "No", "predicted_outcome": "Yes", "customers": matrix["fp"]},
            {"model": model_name, "actual_outcome": "Yes", "predicted_outcome": "No", "customers": matrix["fn"]},
            {"model": model_name, "actual_outcome": "Yes", "predicted_outcome": "Yes", "customers": matrix["tp"]},
        ])
    pd.DataFrame(comparison_rows).to_csv(OUT / "model_comparison.csv", index=False)
    pd.DataFrame(confusion_rows).to_csv(OUT / "confusion_matrix.csv", index=False)
    _write_json(OUT / "metrics.json", {
        "dataset_rows": int(len(clean)),
        "observed_churn_count": int(clean["Churn_Flag"].sum()),
        "observed_churn_rate": float(clean["Churn_Flag"].mean()),
        "train_size": int(len(models["y_train"])),
        "test_size": int(len(models["y_test"])),
        "test_positive_count": int(models["y_test"].sum()),
        "test_positive_prevalence": float(models["y_test"].mean()),
        "random_state": RANDOM_STATE,
        "test_fraction": TEST_SIZE,
        "cross_validation_folds": models["cv_splits"],
        "threshold_selection": "F1 maximization on five-fold out-of-fold training probabilities only",
        "model_selection": {
            "logistic_regression": {"best_params": models["lr_best_params"], "mean_cv_roc_auc": models["lr_cv_roc_auc"]},
            "xgboost": {"best_params": models["xgb_best_params"], "mean_cv_roc_auc": models["xgb_cv_roc_auc"]},
        },
        "test_metrics": metrics,
        "shap": shap_status,
        "model_artifact": artifact_metadata,
        "data_quality_sha256": quality["sha256"],
    })
    _write_json(OUT / "runtime_versions.json", {
        "python": platform.python_version(), "pandas": pd.__version__, "numpy": np.__version__,
        "scikit_learn": sklearn.__version__, "xgboost": xgboost.__version__, "shap": shap.__version__,
        "matplotlib": matplotlib.__version__,
    })
    print(json.dumps({"status": "complete", "rows": len(clean), "train_size": len(models["y_train"]), "test_size": len(models["y_test"]), "metrics": metrics, "shap": shap_status}, indent=2))


if __name__ == "__main__":
    main()
