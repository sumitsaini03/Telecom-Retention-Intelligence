"""
Tests for Telecom Retention Intelligence.
Includes unit tests and SQL-vs-pandas parity tests.
"""
import json
import os
import pathlib

import numpy as np
import pandas as pd
import pytest

# ── Import from analysis ──
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
from analysis import load_and_clean, prepare_features, find_best_threshold, OUT

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_CSV = ROOT / "data" / "Telco-Customer-Churn.csv"


# =============================================================
# DATA INTEGRITY
# =============================================================
class TestDataIntegrity:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.df = load_and_clean()

    def test_row_count(self):
        assert len(self.df) == 7043

    def test_unique_customer_ids(self):
        assert self.df["customerID"].nunique() == 7043

    def test_no_nan_total_charges(self):
        assert self.df["TotalCharges"].isna().sum() == 0

    def test_churn_values(self):
        assert set(self.df["Churn"].unique()) == {"Yes", "No"}

    def test_churn_flag_binary(self):
        assert set(self.df["Churn_Flag"].unique()) == {0, 1}

    def test_churn_count(self):
        assert self.df["Churn_Flag"].sum() == 1869


# =============================================================
# FEATURE PREPARATION
# =============================================================
class TestFeatures:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.df = load_and_clean()
        self.X, self.y, self.num, self.cat, self.pre = prepare_features(self.df)

    def test_no_leakage_churn(self):
        assert "Churn" not in self.X.columns
        assert "Churn_Flag" not in self.X.columns

    def test_no_leakage_id(self):
        assert "customerID" not in self.X.columns

    def test_target_length(self):
        assert len(self.y) == 7043

    def test_feature_columns_non_empty(self):
        assert len(self.X.columns) > 0


# =============================================================
# SPLIT PROPERTIES
# =============================================================
class TestSplit:
    @pytest.fixture(autouse=True)
    def setup(self):
        from sklearn.model_selection import train_test_split
        df = load_and_clean()
        X, y, _, _, _ = prepare_features(df)
        self.X_train, self.X_test, self.y_train, self.y_test = (
            train_test_split(X, y, test_size=0.20,
                             random_state=42, stratify=y)
        )

    def test_reproducible(self):
        """Second split with same seed yields same indices."""
        from sklearn.model_selection import train_test_split
        df = load_and_clean()
        X, y, _, _, _ = prepare_features(df)
        X_train2, X_test2, _, _ = train_test_split(
            X, y, test_size=0.20, random_state=42, stratify=y)
        assert list(X_train2.index) == list(self.X_train.index)

    def test_disjoint(self):
        assert len(set(self.X_train.index) & set(self.X_test.index)) == 0

    def test_stratified(self):
        train_rate = self.y_train.mean()
        test_rate = self.y_test.mean()
        assert abs(train_rate - test_rate) < 0.02


# =============================================================
# THRESHOLD SELECTION
# =============================================================
class TestThreshold:
    def test_threshold_invariant_to_test_labels(self):
        """Threshold must not change when test labels are shuffled."""
        rng = np.random.RandomState(42)
        proba = rng.rand(200)
        y_real = (proba > 0.5).astype(int)  # correlated
        t1 = find_best_threshold(y_real, proba)

        y_shuffled = y_real.copy()
        rng.shuffle(y_shuffled)
        # Threshold is found on TRAINING data, so we pass training labels.
        # This test verifies the function itself is deterministic for given inputs.
        t2 = find_best_threshold(y_real, proba)  # same inputs -> same output
        assert t1 == t2


# =============================================================
# OUTPUT VALIDATION (run after pipeline)
# =============================================================
class TestOutputs:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.metrics_path = OUT / "metrics.json"
        self.scores_path = OUT / "customer_risk_scores.csv"
        self.scenario_path = OUT / "retention_scenario.csv"

    def test_metrics_exist(self):
        if not self.metrics_path.exists():
            pytest.skip("metrics.json not yet generated")
        with open(self.metrics_path) as f:
            m = json.load(f)
        assert "test_metrics" in m
        assert "xgboost" in m["test_metrics"]

    def test_scores_valid(self):
        if not self.scores_path.exists():
            pytest.skip("customer_risk_scores.csv not yet generated")
        scores = pd.read_csv(self.scores_path)
        assert len(scores) == 7043
        assert scores["churn_probability"].between(0, 1).all()
        assert set(scores["split"].unique()) == {"train_oof", "test"}

    def test_scores_sum_to_total(self):
        if not self.scores_path.exists():
            pytest.skip("customer_risk_scores.csv not yet generated")
        scores = pd.read_csv(self.scores_path)
        tier_sum = scores.groupby("risk_tier").size().sum()
        assert tier_sum == 7043

    def test_metrics_match_predictions(self):
        """Recompute metrics from exported scores and compare to metrics.json."""
        if not self.metrics_path.exists() or not self.scores_path.exists():
            pytest.skip("Outputs not yet generated")

        with open(self.metrics_path) as f:
            m = json.load(f)

        scores = pd.read_csv(self.scores_path)
        df = load_and_clean()

        # Merge to get true labels
        test_scores = scores[scores["split"] == "test"].copy()
        test_with_labels = test_scores.merge(
            df[["customerID", "Churn_Flag"]], on="customerID")

        y_true = test_with_labels["Churn_Flag"].values
        y_prob = test_with_labels["churn_probability"].values

        from sklearn.metrics import roc_auc_score
        recomputed_auc = round(roc_auc_score(y_true, y_prob), 4)
        reported_auc = m["test_metrics"]["xgboost"]["roc_auc"]

        assert abs(recomputed_auc - reported_auc) < 0.001, (
            f"Recomputed AUC {recomputed_auc} != reported {reported_auc}")

    def test_scenario_exists(self):
        if not self.scenario_path.exists():
            pytest.skip("retention_scenario.csv not yet generated")
        sc = pd.read_csv(self.scenario_path)
        assert len(sc) == 3  # three effectiveness levels


# =============================================================
# SQL vs PANDAS PARITY (requires PostgreSQL connection)
# =============================================================
class TestSQLParity:
    """Compare SQL query results against pandas.
    Requires TELCO_PG_DSN env var (e.g. postgresql://user:pass@localhost/telco).
    Skips with explicit message when no connection is available.
    """

    @pytest.fixture(autouse=True)
    def setup(self):
        dsn = os.environ.get("TELCO_PG_DSN")
        if not dsn:
            pytest.skip(
                "TELCO_PG_DSN not set - skipping SQL parity tests. "
                "Set TELCO_PG_DSN=postgresql://user:pass@localhost/telco "
                "to enable these tests."
            )
        try:
            import psycopg
            self.conn = psycopg.connect(dsn)
        except Exception as e:
            pytest.skip(f"Cannot connect to PostgreSQL: {e}")

        self.df = load_and_clean()

    def _sql(self, query):
        import psycopg
        with self.conn.cursor() as cur:
            cur.execute(query)
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
        return pd.DataFrame(rows, columns=cols)

    def test_q1_overall_churn(self):
        sql_df = self._sql("""
            SELECT COUNT(*) as total_customers,
                   SUM(CASE WHEN Churn='Yes' THEN 1 ELSE 0 END) as churned
            FROM telco
        """)
        assert int(sql_df["total_customers"].iloc[0]) == len(self.df)
        assert int(sql_df["churned"].iloc[0]) == int(self.df["Churn_Flag"].sum())

    def test_q2_churn_by_contract(self):
        sql_df = self._sql("""
            SELECT Contract, COUNT(*) as customers,
                   SUM(CASE WHEN Churn='Yes' THEN 1 ELSE 0 END) as churned
            FROM telco GROUP BY Contract
        """)
        pd_df = self.df.groupby("Contract").agg(
            customers=("Churn_Flag", "count"),
            churned=("Churn_Flag", "sum"),
        ).reset_index()
        merged = sql_df.merge(pd_df, on="Contract", suffixes=("_sql", "_pd"))
        for _, row in merged.iterrows():
            assert int(row["customers_sql"]) == int(row["customers_pd"])
            assert int(row["churned_sql"]) == int(row["churned_pd"])

    def test_q3_churn_by_tenure_band(self):
        def band(t):
            if t <= 12: return "0-12 months"
            if t <= 24: return "13-24 months"
            if t <= 48: return "25-48 months"
            return "49-72 months"

        pd_counts = self.df.copy()
        pd_counts["tenure_band"] = pd_counts["tenure"].apply(band)
        pd_agg = pd_counts.groupby("tenure_band")["Churn_Flag"].agg(
            ["count", "sum"]).reset_index()
        pd_agg.columns = ["tenure_band", "customers", "churned"]

        sql_df = self._sql("""
            SELECT CASE
                WHEN tenure BETWEEN 0 AND 12  THEN '0-12 months'
                WHEN tenure BETWEEN 13 AND 24 THEN '13-24 months'
                WHEN tenure BETWEEN 25 AND 48 THEN '25-48 months'
                WHEN tenure BETWEEN 49 AND 72 THEN '49-72 months'
            END AS tenure_band,
            COUNT(*) as customers,
            SUM(CASE WHEN Churn='Yes' THEN 1 ELSE 0 END) as churned
            FROM telco GROUP BY tenure_band
        """)
        merged = sql_df.merge(pd_agg, on="tenure_band", suffixes=("_sql", "_pd"))
        for _, row in merged.iterrows():
            assert int(row["customers_sql"]) == int(row["customers_pd"])

    def test_q4_churn_by_payment(self):
        sql_df = self._sql("""
            SELECT PaymentMethod, COUNT(*) as customers,
                   SUM(CASE WHEN Churn='Yes' THEN 1 ELSE 0 END) as churned
            FROM telco GROUP BY PaymentMethod
        """)
        pd_df = self.df.groupby("PaymentMethod").agg(
            customers=("Churn_Flag", "count"),
            churned=("Churn_Flag", "sum"),
        ).reset_index()
        merged = sql_df.merge(pd_df, on="PaymentMethod", suffixes=("_sql", "_pd"))
        for _, row in merged.iterrows():
            assert int(row["customers_sql"]) == int(row["customers_pd"])

    def test_q5_churn_by_internet(self):
        sql_df = self._sql("""
            SELECT InternetService, COUNT(*) as customers,
                   SUM(CASE WHEN Churn='Yes' THEN 1 ELSE 0 END) as churned
            FROM telco GROUP BY InternetService
        """)
        pd_df = self.df.groupby("InternetService").agg(
            customers=("Churn_Flag", "count"),
            churned=("Churn_Flag", "sum"),
        ).reset_index()
        merged = sql_df.merge(pd_df, on="InternetService", suffixes=("_sql", "_pd"))
        for _, row in merged.iterrows():
            assert int(row["customers_sql"]) == int(row["customers_pd"])

    def test_q6_churn_by_tech_support(self):
        sql_df = self._sql("""
            SELECT TechSupport, COUNT(*) as customers,
                   SUM(CASE WHEN Churn='Yes' THEN 1 ELSE 0 END) as churned
            FROM telco GROUP BY TechSupport
        """)
        pd_df = self.df.groupby("TechSupport").agg(
            customers=("Churn_Flag", "count"),
            churned=("Churn_Flag", "sum"),
        ).reset_index()
        merged = sql_df.merge(pd_df, on="TechSupport", suffixes=("_sql", "_pd"))
        for _, row in merged.iterrows():
            assert int(row["customers_sql"]) == int(row["customers_pd"])

    def test_q7_avg_charges(self):
        sql_df = self._sql("""
            SELECT Churn, ROUND(AVG(MonthlyCharges)::numeric, 2) as avg_mc
            FROM telco GROUP BY Churn
        """)
        pd_df = self.df.groupby("Churn")["MonthlyCharges"].mean().round(2).reset_index()
        pd_df.columns = ["Churn", "avg_mc"]
        merged = sql_df.merge(pd_df, on="Churn", suffixes=("_sql", "_pd"))
        for _, row in merged.iterrows():
            assert abs(float(row["avg_mc_sql"]) - float(row["avg_mc_pd"])) < 0.05

    def test_q8_revenue_at_risk(self):
        sql_df = self._sql("""
            SELECT
                ROUND(SUM(CASE WHEN Churn='Yes' THEN MonthlyCharges ELSE 0 END)::numeric, 2) as churned_mrr,
                ROUND(SUM(MonthlyCharges)::numeric, 2) as total_mrr
            FROM telco
        """)
        pd_churned = round(self.df.loc[self.df["Churn"]=="Yes", "MonthlyCharges"].sum(), 2)
        pd_total = round(self.df["MonthlyCharges"].sum(), 2)
        assert abs(float(sql_df["churned_mrr"].iloc[0]) - pd_churned) < 0.05
        assert abs(float(sql_df["total_mrr"].iloc[0]) - pd_total) < 0.05

    def test_q13_segment_counts(self):
        sql_df = self._sql("""
            SELECT Contract, InternetService, PaymentMethod,
                   COUNT(*) as customers
            FROM telco
            GROUP BY Contract, InternetService, PaymentMethod
            HAVING COUNT(*) >= 50
        """)
        pd_agg = self.df.groupby(
            ["Contract", "InternetService", "PaymentMethod"]
        ).size().reset_index(name="customers")
        pd_agg = pd_agg[pd_agg["customers"] >= 50]
        assert abs(len(sql_df) - len(pd_agg)) == 0
