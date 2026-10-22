"""Load the verified project data and execute every named PostgreSQL analysis."""

from __future__ import annotations

import json
import os
import re
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
import psycopg

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.analysis import DATA_CSV, OUT, business_aggregates, validate_and_clean

def query_blocks(sql_text: str) -> dict[str, str]:
    pieces = re.split(r"(?m)^-- query: ([a-z0-9_]+)\s*$", sql_text)
    if len(pieces) < 3 or len(pieces) % 2 != 1:
        raise ValueError("SQL query file must contain named '-- query: name' blocks")
    return {pieces[index].strip(): pieces[index + 1].strip() for index in range(1, len(pieces), 2)}


def json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value


def execute_analysis(dsn: str | None = None) -> dict[str, Any]:
    dsn = dsn or os.environ.get("TELCO_PG_DSN")
    if not dsn:
        raise ValueError("Set TELCO_PG_DSN to the local PostgreSQL connection string before running SQL analysis")
    clean, quality = validate_and_clean(DATA_CSV)
    score_path = OUT / "customer_risk_scores.csv"
    if not score_path.is_file():
        raise FileNotFoundError("Run `python src/analysis.py` before PostgreSQL validation; customer_risk_scores.csv is missing.")
    scores = pd.read_csv(score_path)
    if len(scores) != len(clean) or scores["customerID"].astype(str).duplicated().any():
        raise ValueError("Customer risk output is incomplete or contains duplicate customer identifiers")

    schema_text = (ROOT / "sql" / "schema.sql").read_text(encoding="utf-8")
    blocks = query_blocks((ROOT / "sql" / "analysis.sql").read_text(encoding="utf-8"))
    query_results: dict[str, list[dict[str, Any]]] = {}
    with psycopg.connect(dsn) as connection:
        with connection.cursor() as cursor:
            # Schema statements are simple DDL statements; keep them inside the same transaction as reload.
            for statement in schema_text.split(";"):
                if statement.strip():
                    cursor.execute(statement)
            cursor.execute("TRUNCATE TABLE telco_model_scores, telco_customers")
            customer_columns = [
                "customerID", "gender", "SeniorCitizen", "Partner", "Dependents", "tenure",
                "PhoneService", "MultipleLines", "InternetService", "OnlineSecurity", "OnlineBackup",
                "DeviceProtection", "TechSupport", "StreamingTV", "StreamingMovies", "Contract",
                "PaperlessBilling", "PaymentMethod", "MonthlyCharges", "TotalCharges", "Churn",
            ]
            insert_customers = """INSERT INTO telco_customers (
                customer_id, gender, senior_citizen, partner, dependents, tenure, phone_service,
                multiple_lines, internet_service, online_security, online_backup, device_protection,
                tech_support, streaming_tv, streaming_movies, contract, paperless_billing,
                payment_method, monthly_charges, total_charges, churn
            ) VALUES (""" + ",".join(["%s"] * len(customer_columns)) + ")"
            customer_rows = (
                tuple(value.item() if hasattr(value, "item") else value for value in row)
                for row in clean[customer_columns].itertuples(index=False, name=None)
            )
            cursor.executemany(insert_customers, customer_rows)

            insert_scores = """INSERT INTO telco_model_scores (
                customer_id, observed_churn, churn_probability, predicted_churn,
                risk_tier, model_identifier, data_split
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)"""
            score_columns = [
                "customerID", "observed_churn", "churn_probability", "predicted_churn",
                "risk_tier", "model_identifier", "data_split",
            ]
            def score_rows():
                for row in scores[score_columns].itertuples(index=False, name=None):
                    yield (
                        str(row[0]), str(row[1]), float(row[2]), int(row[3]),
                        str(row[4]), str(row[5]), str(row[6]),
                    )

            cursor.executemany(insert_scores, score_rows())

            cursor.execute("SHOW server_version")
            database_version = cursor.fetchone()[0]
            for name, query in blocks.items():
                cursor.execute(query.rstrip().rstrip(";"))
                field_names = [column.name for column in cursor.description]
                query_results[name] = [dict(zip(field_names, row)) for row in cursor.fetchall()]
        # connection context commits only after all business queries complete successfully.

    aggregates, adoption = business_aggregates(clean)
    comparisons: dict[str, Any] = {}
    overall = query_results["overall_churn"][0]
    comparisons["total_customers"] = int(overall["total_customers"]) == len(clean)
    comparisons["churned_customers"] = int(overall["churned_customers"]) == int(clean["Churn_Flag"].sum())
    comparisons["overall_churn_rate"] = abs(float(overall["churn_rate"]) - float(clean["Churn_Flag"].mean())) < 1e-12

    def compare_segment_query(query_name: str, dimension: str) -> bool:
        sql_rows = {str(row["segment_value"]): row for row in query_results[query_name]}
        pandas_rows = aggregates.loc[aggregates["dimension"].eq(dimension)].set_index("segment_value")
        if set(sql_rows) != set(str(key) for key in pandas_rows.index):
            return False
        for label, sql_row in sql_rows.items():
            pandas_row = pandas_rows.loc[label]
            if int(sql_row["customers"]) != int(pandas_row["customers"]):
                return False
            if int(sql_row["churned"]) != int(pandas_row["churned"]):
                return False
            if abs(float(sql_row["churn_rate"]) - float(pandas_row["churn_rate"])) > 1e-12:
                return False
        return True

    comparisons["churn_by_contract"] = compare_segment_query("churn_by_contract", "Contract")
    comparisons["churn_by_tenure_band"] = compare_segment_query("churn_by_tenure", "tenure_band")
    comparisons["churn_by_payment_method"] = compare_segment_query("churn_by_payment_method", "PaymentMethod")

    addon_sql = {row["segment_value"]: row for row in query_results["addon_adoption_internet_only"]}
    internet_customers = clean.loc[clean["InternetService"].ne("No")]
    addon_columns = {
        "OnlineSecurity": "OnlineSecurity", "OnlineBackup": "OnlineBackup",
        "DeviceProtection": "DeviceProtection", "TechSupport": "TechSupport",
        "StreamingTV": "StreamingTV", "StreamingMovies": "StreamingMovies",
    }
    comparisons["addon_adoption_internet_only"] = True
    for addon_name, column in addon_columns.items():
        sql_row = addon_sql[addon_name]
        expected_adopters = int(internet_customers[column].eq("Yes").sum())
        comparisons["addon_adoption_internet_only"] &= (
            int(sql_row["internet_customers"]) == len(internet_customers)
            and int(sql_row["adopters"]) == expected_adopters
        )
    comparisons["addon_denominator_excludes_no_internet"] = all(
        int(row["internet_customers"]) == len(internet_customers)
        for row in query_results["addon_adoption_internet_only"]
    )

    addon_sql_rates = {int(row["segment_value"]): row for row in query_results["churn_by_addon_count"]}
    comparisons["churn_by_addon_count_internet_only"] = True
    for row in adoption.itertuples(index=False):
        sql_row = addon_sql_rates[int(row.addon_count)]
        comparisons["churn_by_addon_count_internet_only"] &= (
            int(sql_row["customers"]) == int(row.customers)
            and int(sql_row["churned"]) == int(row.churned)
        )

    report = {
        "status": "passed" if all(comparisons.values()) else "failed",
        "database_version": database_version,
        "source_sha256": quality["sha256"],
        "customers_loaded": len(clean),
        "risk_rows_loaded": len(scores),
        "queries_executed": list(blocks),
        "comparisons": comparisons,
        "all_parity_checks_passed": all(comparisons.values()),
        "query_results": json_safe(query_results),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "postgres_validation.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if not report["all_parity_checks_passed"]:
        raise AssertionError(f"PostgreSQL/Pandas parity failure: {comparisons}")
    return report


if __name__ == "__main__":
    result = execute_analysis()
    print(json.dumps({key: value for key, value in result.items() if key != "query_results"}, indent=2))
