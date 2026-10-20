"""
Telecom Retention Intelligence - Analysis Pipeline
===================================================
Single script: clean, EDA, model, SHAP, export.
Dataset: IBM Telco Customer Churn (7,043 rows, 21 columns).
"""

import json
import warnings
import pathlib

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.model_selection import train_test_split, StratifiedKFold, GridSearchCV
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    roc_auc_score, average_precision_score,
    precision_score, recall_score, f1_score,
    confusion_matrix, classification_report,
    roc_curve, precision_recall_curve,
)
import xgboost as xgb
import shap

warnings.filterwarnings("ignore", category=FutureWarning)

# ── Paths ──────────────────────────────────────────────────
ROOT     = pathlib.Path(__file__).resolve().parent.parent
DATA_CSV = ROOT / "data" / "Telco-Customer-Churn.csv"
OUT      = ROOT / "outputs"
OUT.mkdir(exist_ok=True)

# ── Retention-scenario constants (hypothetical) ───────────
COST_PER_CUSTOMER   = 50      # USD, hypothetical campaign cost
MONTHS_RETAINED     = 6       # months of revenue if customer stays
EFFECTIVENESS_LEVELS = [0.05, 0.10, 0.15]  # hypothetical

RANDOM_STATE = 42

# =============================================================
# 1. LOAD AND CLEAN
# =============================================================
def load_and_clean(path=DATA_CSV):
    """Load IBM Telco CSV; fix blanks in TotalCharges; return DataFrame."""
    df = pd.read_csv(path)

    # Validate shape and uniqueness
    assert df.shape == (7043, 21), f"Unexpected shape: {df.shape}"
    assert df["customerID"].nunique() == 7043, "Duplicate customerIDs"

    # Fix blank TotalCharges (11 rows with tenure=0)
    df["TotalCharges"] = pd.to_numeric(df["TotalCharges"], errors="coerce")
    df["TotalCharges"] = df["TotalCharges"].fillna(0.0)

    # Binary target
    df["Churn_Flag"] = (df["Churn"] == "Yes").astype(int)

    return df


# =============================================================
# 2. EDA CHARTS
# =============================================================
def run_eda(df):
    """Save EDA charts to outputs/."""
    plt.style.use("seaborn-v0_8-whitegrid")
    colors = {"No": "#2b6cb0", "Yes": "#c53030"}

    # ── Chart 1: Churn distribution ──
    fig, ax = plt.subplots(figsize=(6, 4))
    counts = df["Churn"].value_counts()
    bars = ax.bar(counts.index, counts.values,
                  color=[colors[k] for k in counts.index], edgecolor="white")
    for b in bars:
        ax.text(b.get_x() + b.get_width()/2, b.get_height() + 40,
                f"{int(b.get_height()):,}", ha="center", fontsize=11)
    ax.set_title("Churn Distribution", fontsize=14, fontweight="bold")
    ax.set_ylabel("Customers")
    fig.tight_layout()
    fig.savefig(OUT / "churn_distribution.png", dpi=150)
    plt.close(fig)

    # ── Chart 2: Churn by contract ──
    fig, ax = plt.subplots(figsize=(7, 4))
    ct = df.groupby("Contract")["Churn_Flag"].agg(["count", "sum", "mean"])
    ct = ct.sort_values("mean", ascending=False)
    bars = ax.bar(ct.index, ct["mean"] * 100,
                  color="#c53030", edgecolor="white")
    for b, (_, row) in zip(bars, ct.iterrows()):
        ax.text(b.get_x() + b.get_width()/2, b.get_height() + 0.8,
                f"{row['mean']*100:.1f}%", ha="center", fontsize=10)
    ax.set_title("Churn Rate by Contract Type", fontsize=14, fontweight="bold")
    ax.set_ylabel("Churn Rate (%)")
    fig.tight_layout()
    fig.savefig(OUT / "churn_by_contract.png", dpi=150)
    plt.close(fig)

    # ── Chart 3: Churn by tenure band ──
    def tenure_band(t):
        if t <= 12: return "0-12 mo"
        if t <= 24: return "13-24 mo"
        if t <= 48: return "25-48 mo"
        return "49-72 mo"

    df["tenure_band"] = df["tenure"].apply(tenure_band)
    band_order = ["0-12 mo", "13-24 mo", "25-48 mo", "49-72 mo"]
    fig, ax = plt.subplots(figsize=(7, 4))
    tb = df.groupby("tenure_band")["Churn_Flag"].mean().reindex(band_order) * 100
    ax.bar(tb.index, tb.values, color="#2b6cb0", edgecolor="white")
    for i, v in enumerate(tb.values):
        ax.text(i, v + 0.5, f"{v:.1f}%", ha="center", fontsize=10)
    ax.set_title("Churn Rate by Tenure Band", fontsize=14, fontweight="bold")
    ax.set_ylabel("Churn Rate (%)")
    fig.tight_layout()
    fig.savefig(OUT / "churn_by_tenure.png", dpi=150)
    plt.close(fig)
    df.drop(columns=["tenure_band"], inplace=True)

    # ── Chart 4: Monthly charges distribution ──
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.hist(df.loc[df["Churn"] == "No", "MonthlyCharges"],
            bins=30, alpha=0.6, label="Retained", color="#2b6cb0")
    ax.hist(df.loc[df["Churn"] == "Yes", "MonthlyCharges"],
            bins=30, alpha=0.6, label="Churned", color="#c53030")
    ax.set_title("Monthly Charges Distribution", fontsize=14, fontweight="bold")
    ax.set_xlabel("Monthly Charges ($)")
    ax.set_ylabel("Customers")
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT / "monthly_charges_dist.png", dpi=150)
    plt.close(fig)

    print("  EDA charts saved.")


# =============================================================
# 3. FEATURE ENGINEERING AND SPLIT
# =============================================================
def prepare_features(df):
    """Return X, y, feature-column lists, and the preprocessor."""
    drop_cols = ["customerID", "Churn", "Churn_Flag"]
    X = df.drop(columns=drop_cols)
    y = df["Churn_Flag"].values

    num_cols = X.select_dtypes(include="number").columns.tolist()
    cat_cols = X.select_dtypes(include=["object", "string"]).columns.tolist()

    preprocessor = ColumnTransformer([
        ("num", StandardScaler(), num_cols),
        ("cat", OneHotEncoder(drop="first", sparse_output=False,
                              handle_unknown="infrequent_if_exist"), cat_cols),
    ])

    return X, y, num_cols, cat_cols, preprocessor


# =============================================================
# 4. MODEL TRAINING
# =============================================================
def find_best_threshold(y_true, proba):
    """Threshold that maximises F1 on the given labels/probabilities."""
    best_f1, best_t = 0.0, 0.5
    for t in np.arange(0.10, 0.90, 0.01):
        preds = (proba >= t).astype(int)
        f1 = f1_score(y_true, preds, zero_division=0)
        if f1 > best_f1:
            best_f1, best_t = f1, t
    return round(float(best_t), 2)


def train_models(X, y, preprocessor):
    """Train logistic regression + XGBoost; return models and metadata."""
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=RANDOM_STATE, stratify=y
    )

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)

    # ── Logistic Regression ──
    lr_pipe = Pipeline([
        ("pre", preprocessor),
        ("clf", LogisticRegression(max_iter=1000, random_state=RANDOM_STATE)),
    ])
    lr_pipe.fit(X_train, y_train)

    # OOF predictions for threshold selection (training set only)
    lr_oof = np.zeros(len(y_train))
    for fold_train, fold_val in cv.split(X_train, y_train):
        fold_pipe = Pipeline([
            ("pre", preprocessor),
            ("clf", LogisticRegression(max_iter=1000, random_state=RANDOM_STATE)),
        ])
        fold_pipe.fit(X_train.iloc[fold_train], y_train[fold_train])
        lr_oof[fold_val] = fold_pipe.predict_proba(
            X_train.iloc[fold_val])[:, 1]
    lr_threshold = find_best_threshold(y_train, lr_oof)

    # ── XGBoost with grid search ──
    xgb_pipe = Pipeline([
        ("pre", preprocessor),
        ("clf", xgb.XGBClassifier(
            eval_metric="logloss",
            random_state=RANDOM_STATE,
        )),
    ])

    param_grid = {
        "clf__n_estimators":  [100, 200],
        "clf__max_depth":     [4, 6],
        "clf__learning_rate": [0.05, 0.1],
    }

    gs = GridSearchCV(
        xgb_pipe, param_grid, cv=cv, scoring="roc_auc",
        n_jobs=-1, refit=True,
    )
    gs.fit(X_train, y_train)
    xgb_best = gs.best_estimator_
    print(f"  XGBoost best params: {gs.best_params_}")
    print(f"  XGBoost best CV ROC-AUC: {gs.best_score_:.4f}")

    # OOF predictions for XGBoost threshold
    xgb_oof = np.zeros(len(y_train))
    for fold_train, fold_val in cv.split(X_train, y_train):
        fold_pipe = Pipeline([
            ("pre", preprocessor),
            ("clf", xgb.XGBClassifier(
                **{k.replace("clf__", ""): v
                   for k, v in gs.best_params_.items()},
                eval_metric="logloss",
                random_state=RANDOM_STATE,
            )),
        ])
        fold_pipe.fit(X_train.iloc[fold_train], y_train[fold_train])
        xgb_oof[fold_val] = fold_pipe.predict_proba(
            X_train.iloc[fold_val])[:, 1]
    xgb_threshold = find_best_threshold(y_train, xgb_oof)

    return {
        "lr_pipe": lr_pipe,
        "xgb_pipe": xgb_best,
        "lr_threshold": lr_threshold,
        "xgb_threshold": xgb_threshold,
        "lr_oof_proba": lr_oof,
        "xgb_oof_proba": xgb_oof,
        "xgb_best_params": gs.best_params_,
        "xgb_cv_auc": gs.best_score_,
        "X_train": X_train,
        "X_test": X_test,
        "y_train": y_train,
        "y_test": y_test,
    }


# =============================================================
# 5. EVALUATION
# =============================================================
def evaluate(models):
    """Evaluate both models on the held-out test set (one-time)."""
    results = {}
    for name, pipe_key, thresh_key in [
        ("logistic_regression", "lr_pipe", "lr_threshold"),
        ("xgboost", "xgb_pipe", "xgb_threshold"),
    ]:
        pipe = models[pipe_key]
        threshold = models[thresh_key]
        X_test = models["X_test"]
        y_test = models["y_test"]

        proba = pipe.predict_proba(X_test)[:, 1]
        preds = (proba >= threshold).astype(int)

        results[name] = {
            "threshold": threshold,
            "roc_auc":   round(roc_auc_score(y_test, proba), 4),
            "pr_auc":    round(average_precision_score(y_test, proba), 4),
            "precision": round(precision_score(y_test, preds, zero_division=0), 4),
            "recall":    round(recall_score(y_test, preds, zero_division=0), 4),
            "f1":        round(f1_score(y_test, preds, zero_division=0), 4),
        }
        print(f"  {name}: {results[name]}")

    return results


# =============================================================
# 6. SHAP EXPLANATIONS
# =============================================================
def explain_shap(pipe_or_models, X=None, out_dir=OUT):
    """TreeSHAP on the XGBoost pipeline; save beeswarm, bar, and waterfall plots."""
    if isinstance(pipe_or_models, dict):
        pipe = pipe_or_models["xgb_pipe"]
        X = pipe_or_models["X_test"]
    else:
        pipe = pipe_or_models
        if X is None:
            raise ValueError("X must be provided when passing pipeline directly")

    prep, clf = pipe[:-1], pipe[-1]
    X_t = prep.transform(X)
    if hasattr(X_t, "toarray"):
        X_t = X_t.toarray()
    X_t = pd.DataFrame(X_t, columns=prep.get_feature_names_out(), index=X.index)

    sv = shap.TreeExplainer(clf.get_booster())(X_t)

    out = pathlib.Path(out_dir)
    out.mkdir(exist_ok=True)

    # ── Beeswarm summary plot ──
    shap.plots.beeswarm(sv, max_display=15, show=False)
    plt.title("SHAP Feature Importance (XGBoost)", fontsize=14, fontweight="bold")
    plt.tight_layout()
    plt.savefig(out / "shap_summary.png", dpi=150, bbox_inches="tight")
    plt.close()

    # ── Bar plot ──
    shap.plots.bar(sv, max_display=15, show=False)
    plt.title("SHAP Mean |SHAP| (XGBoost)", fontsize=14, fontweight="bold")
    plt.tight_layout()
    plt.savefig(out / "shap_bar.png", dpi=150, bbox_inches="tight")
    plt.close()

    # ── Single-customer waterfall (customer with highest risk) ──
    top = int(np.argmax(sv.base_values + sv.values.sum(axis=1)))
    shap.plots.waterfall(sv[top], max_display=12, show=False)
    plt.title("SHAP Waterfall - Highest Risk Customer", fontsize=12, fontweight="bold")
    plt.tight_layout()
    plt.savefig(out / "shap_waterfall.png", dpi=150, bbox_inches="tight")
    plt.close()

    print("  SHAP plots saved.")


# =============================================================
# 7. ROC & PR CURVES
# =============================================================
def plot_curves(models):
    """ROC and PR curves for both models."""
    X_test = models["X_test"]
    y_test = models["y_test"]

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    for name, pipe_key, color in [
        ("Logistic Regression", "lr_pipe", "#2b6cb0"),
        ("XGBoost", "xgb_pipe", "#c53030"),
    ]:
        proba = models[pipe_key].predict_proba(X_test)[:, 1]

        # ROC
        fpr, tpr, _ = roc_curve(y_test, proba)
        auc_val = roc_auc_score(y_test, proba)
        axes[0].plot(fpr, tpr, label=f"{name} (AUC={auc_val:.3f})", color=color)

        # PR
        prec, rec, _ = precision_recall_curve(y_test, proba)
        pr_auc = average_precision_score(y_test, proba)
        axes[1].plot(rec, prec, label=f"{name} (AP={pr_auc:.3f})", color=color)

    axes[0].plot([0,1], [0,1], "k--", alpha=0.3)
    axes[0].set_title("ROC Curve", fontsize=14, fontweight="bold")
    axes[0].set_xlabel("False Positive Rate")
    axes[0].set_ylabel("True Positive Rate")
    axes[0].legend()

    baseline = y_test.mean()
    axes[1].axhline(baseline, color="grey", linestyle="--", alpha=0.4,
                    label=f"Baseline ({baseline:.2f})")
    axes[1].set_title("Precision-Recall Curve", fontsize=14, fontweight="bold")
    axes[1].set_xlabel("Recall")
    axes[1].set_ylabel("Precision")
    axes[1].legend()

    fig.tight_layout()
    fig.savefig(OUT / "roc_pr_curves.png", dpi=150)
    plt.close(fig)
    print("  ROC/PR curves saved.")


# =============================================================
# 8. EXPORT PREDICTIONS AND METRICS
# =============================================================
def export_results(df, models, metrics):
    """Export metrics.json, customer_risk_scores.csv, retention_scenario.csv."""

    # ── 8a. metrics.json ──
    meta = {
        "dataset_rows": len(df),
        "churn_rate": round(df["Churn_Flag"].mean(), 4),
        "train_size": len(models["y_train"]),
        "test_size": len(models["y_test"]),
        "xgb_best_params": models["xgb_best_params"],
        "xgb_cv_roc_auc": round(models["xgb_cv_auc"], 4),
        "lr_threshold": models["lr_threshold"],
        "xgb_threshold": models["xgb_threshold"],
        "test_metrics": metrics,
    }
    with open(OUT / "metrics.json", "w") as f:
        json.dump(meta, f, indent=2)
    print("  metrics.json saved.")

    # ── 8b. Customer risk scores ──
    # Training customers: OOF probabilities (not in-sample)
    # Test customers: final model probabilities
    # Column 'split' marks provenance
    xgb_pipe = models["xgb_pipe"]
    xgb_threshold = models["xgb_threshold"]

    train_idx = models["X_train"].index
    test_idx  = models["X_test"].index

    scores = df[["customerID", "Churn"]].copy()
    scores["churn_probability"] = np.nan
    scores["split"] = ""

    # Training: out-of-fold probabilities
    scores.loc[train_idx, "churn_probability"] = models["xgb_oof_proba"]
    scores.loc[train_idx, "split"] = "train_oof"

    # Test: final model probabilities
    test_proba = xgb_pipe.predict_proba(models["X_test"])[:, 1]
    scores.loc[test_idx, "churn_probability"] = test_proba
    scores.loc[test_idx, "split"] = "test"

    # Risk tiers based on training-selected threshold
    def risk_tier(p):
        if p >= xgb_threshold + 0.15:
            return "Critical"
        elif p >= xgb_threshold:
            return "High"
        elif p >= xgb_threshold - 0.15:
            return "Medium"
        else:
            return "Low"

    scores["risk_tier"] = scores["churn_probability"].apply(risk_tier)
    scores["churn_probability"] = scores["churn_probability"].round(4)
    scores.to_csv(OUT / "customer_risk_scores.csv", index=False)
    print(f"  customer_risk_scores.csv saved ({len(scores)} rows).")

    # ── 8c. Retention scenario ──
    # Identify top segment by churned MRR
    df_temp = df.copy()
    df_temp["segment"] = (
        df_temp["Contract"] + " | " +
        df_temp["InternetService"] + " | " +
        df_temp["PaymentMethod"]
    )
    seg_stats = df_temp.groupby("segment").agg(
        customers=("Churn_Flag", "count"),
        churned=("Churn_Flag", "sum"),
        avg_monthly=("MonthlyCharges", "mean"),
    ).reset_index()
    seg_stats["churn_rate"] = seg_stats["churned"] / seg_stats["customers"]
    seg_stats["churned_mrr"] = seg_stats["churned"] * seg_stats["avg_monthly"]
    seg_stats = seg_stats[seg_stats["customers"] >= 50]
    top_seg = seg_stats.sort_values("churned_mrr", ascending=False).iloc[0]

    scenarios = []
    for eff in EFFECTIVENESS_LEVELS:
        retained = top_seg["churned"] * eff
        revenue_saved = retained * top_seg["avg_monthly"] * MONTHS_RETAINED
        campaign_cost = top_seg["customers"] * COST_PER_CUSTOMER
        net_value = revenue_saved - campaign_cost
        breakeven = campaign_cost / (top_seg["churned"] * top_seg["avg_monthly"]
                                     * MONTHS_RETAINED) if top_seg["churned"] > 0 else None
        scenarios.append({
            "segment": top_seg["segment"],
            "segment_size": int(top_seg["customers"]),
            "baseline_churned": int(top_seg["churned"]),
            "baseline_churn_rate": round(top_seg["churn_rate"], 4),
            "avg_monthly_charge": round(top_seg["avg_monthly"], 2),
            "effectiveness_assumption": eff,
            "customers_retained_hypothetical": round(retained, 1),
            "revenue_saved_hypothetical": round(revenue_saved, 2),
            "campaign_cost_hypothetical": round(campaign_cost, 2),
            "net_value_hypothetical": round(net_value, 2),
            "breakeven_effectiveness": round(breakeven, 4) if breakeven else None,
            "cost_per_customer": COST_PER_CUSTOMER,
            "months_retained_assumed": MONTHS_RETAINED,
            "NOTE": "Effectiveness is hypothetical. An A/B test is the recommended next step.",
        })

    scenario_df = pd.DataFrame(scenarios)
    scenario_df.to_csv(OUT / "retention_scenario.csv", index=False)
    print("  retention_scenario.csv saved.")

    return scores


# =============================================================
# MAIN
# =============================================================
def main():
    print("=" * 60)
    print("Telecom Retention Intelligence - Analysis Pipeline")
    print("=" * 60)

    print("\n[1/7] Loading and cleaning data...")
    df = load_and_clean()
    print(f"  {len(df)} rows, churn rate: {df['Churn_Flag'].mean():.4f}")

    print("\n[2/7] Running EDA...")
    run_eda(df)

    print("\n[3/7] Preparing features...")
    X, y, num_cols, cat_cols, preprocessor = prepare_features(df)
    print(f"  Numeric: {num_cols}")
    print(f"  Categorical: {cat_cols}")

    print("\n[4/7] Training models...")
    models = train_models(X, y, preprocessor)
    print(f"  LR threshold (from OOF): {models['lr_threshold']}")
    print(f"  XGB threshold (from OOF): {models['xgb_threshold']}")

    print("\n[5/7] Evaluating on test set (one-time)...")
    metrics = evaluate(models)

    print("\n[6/7] SHAP explanations...")
    explain_shap(models)
    plot_curves(models)

    print("\n[7/7] Exporting results...")
    export_results(df, models, metrics)

    print("\n" + "=" * 60)
    print("Pipeline complete. All outputs in: outputs/")
    print("=" * 60)


if __name__ == "__main__":
    main()
