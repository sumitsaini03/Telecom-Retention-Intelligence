# Implementation Status

Validation date: 2026-10-22 (Asia/Calcutta)

## Completed and verified

- Downloaded and byte-verified the authentic IBM Telco Customer Churn CSV. The source has 7,043 rows and 21 columns; its SHA-256 and retrieval metadata are recorded in `data/source_metadata.json`.
- Built and ran the deterministic Python pipeline. It validates and cleans the data, creates business aggregates and charts, compares logistic regression with XGBoost, selects thresholds from training out-of-fold predictions, evaluates once on the holdout, computes TreeSHAP explanations, and exports provenance-labeled risk scores.
- A recorded PostgreSQL 16.15 run on 2026-10-20 loaded the customer and risk tables, executed all 14 named SQL analyses, and passed all nine independent Pandas parity checks. Internet add-on rates use the 5,517 customers with internet service as their denominator. That checked-in artifact predates the final analytics refresh.
- A GitHub Actions run regenerated the current scores and passed the PostgreSQL 16 integration test and all nine Pandas parity checks. The local pytest run was **20 passed, 1 skipped, 0 failed**; the skip was the PostgreSQL integration test because `TELCO_PG_DSN` was not configured and Docker's local engine pipe was unavailable.
- Created setup instructions, data and model cards, methodology, business insights, validation evidence, resume material, run scripts, pinned dependency versions, and the Power BI source project.
- Built `powerbi/TelecomRetention/TelecomRetention.pbip`: six PBIR pages, a nine-table TMDL model, typed Power Query M imports, 28 described DAX measures, four overview dropdown slicers, and a custom theme. The Microsoft PBIR validator passed with zero errors and warnings. Current prepared data reconciles 7,043 customers and the 1,409-row held-out model outputs.

## Remaining verification

- Power BI Desktop 2.159.883.0 is installed. The Desktop Bridge launch attempt left only blank `Untitled - Power BI Desktop` instances with no PBIP folder reported as open. The Desktop preview returned `HOST_UNAVAILABLE`.
- Desktop semantic-model acceptance, Power Query refresh, DAX execution, visual layout and slicer behavior, and genuine screenshots remain unverified. No PBIX cache or screenshot is included. The PBIP/PBIR source project exists and its report schema passes; it is not described as visually inspected in Desktop.
- A local PostgreSQL rerun still requires Docker Desktop and a configured `TELCO_PG_DSN`; the current SQL integration has passed in GitHub Actions.

See `VALIDATION_REPORT.md` for project-wide checks and `powerbi/VALIDATION_REPORT.md` for Power BI-specific results. See `powerbi/README.md` for Windows open, refresh, data model, and page instructions.
