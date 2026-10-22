"""Real PostgreSQL integration test (requires TELCO_PG_DSN and a disposable DB)."""

import os

import pytest

from scripts.run_postgres import execute_analysis

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.environ.get("TELCO_PG_DSN"), reason="TELCO_PG_DSN is not configured"),
]


def test_postgres_queries_execute_and_match_independent_pandas_aggregates():
    result = execute_analysis(os.environ["TELCO_PG_DSN"])
    assert result["status"] == "passed"
    assert result["database_version"]
    assert result["customers_loaded"] == 7043
    assert result["all_parity_checks_passed"]
    assert result["comparisons"]["addon_denominator_excludes_no_internet"]
    assert len(result["queries_executed"]) >= 14
