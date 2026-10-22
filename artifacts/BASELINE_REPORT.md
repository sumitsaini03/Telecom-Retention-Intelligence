# Baseline Audit (Before Implementation)

Audit date: 2026-10-20 (Asia/Calcutta)

## Repository and prior claims

- Initial commit: `5479081` (`Add complete telecom churn intelligence pipeline, SQL queries, ML models, test suite, and Power BI assets`).
- Existing source areas: `src/analysis.py`, `sql/analysis.sql`, `tests/`, `data/`, `outputs/`, and `powerbi/`.
- The README reported metrics and an earlier test total, but these were not treated as current evidence. The existing outputs predated this clean run and the README itself stated that Power BI and PostgreSQL had not been validated.
- The existing SQL already filtered `InternetService <> 'No'` for its protective add-on query. The revised SQL keeps and makes that denominator rule explicit for all add-on adoption measures.

## Environment observed

| Check | Baseline result |
|---|---|
| System Python | 3.14.6; only `pip` was installed |
| Bundled project runtime | Python 3.12.14; initially had NumPy and Pandas only |
| Test command | `python -m pytest -q --junitxml=outputs\\baseline-test-results.xml` failed before collection: `No module named pytest` |
| PostgreSQL client | `psql`, `createdb`, and `pg_ctl` were not on PATH |
| Docker client | 29.8.2 present; Docker engine initially stopped |
| Power BI Desktop | Expected executable paths and app package were absent |
| IBM source URL | Network request in the default sandbox was blocked; elevated fetch returned HTTP 200 |

Docker Desktop was subsequently launched for the requested PostgreSQL integration attempt. The Python dependencies were installed into a temporary directory (`C:\\tmp\\telecom-retention-deps`) and the final runtime/version check is recorded in `outputs/runtime_versions.json` after the pipeline run.

## Source data check

The local `data/Telco-Customer-Churn.csv` was compared byte-for-byte with the IBM raw URL download. Both files were 970,457 bytes with SHA-256 `16320C9C1EC72448DB59AA0A26A0B95401046BEF5D02FD3AEB906448E3055E91`. The source had 7,043 rows, 21 columns, 7,043 unique IDs, 1,869 `Yes` churn labels, and 11 blank `TotalCharges` values; all 11 blanks were zero-tenure rows and none was marked churned.

## Baseline test result

The existing suite was invoked before source changes. It did not collect or execute tests because pytest was missing from the system Python. Thus the former README statement “19 passed, 9 skipped” was not independently reproducible in the initial environment. Final results are reported separately in `VALIDATION_REPORT.md`.
