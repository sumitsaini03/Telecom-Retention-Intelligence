# Validation Report

Validation date: 2026-10-22 (Asia/Calcutta)

## Dataset validation — passed

- Source URL: `https://raw.githubusercontent.com/IBM/telco-customer-churn-on-icp4d/master/data/Telco-Customer-Churn.csv`
- HTTP status: 200; final URL is the same raw GitHub URL.
- Bytes: 970,457; SHA-256: `16320c9c1ec72448db59aa0a26a0b95401046bef5d02fd3aeb906448e3055e91`.
- Verified source shape: 7,043 rows x 21 columns; 7,043 unique customer IDs; 5,174 `No` and 1,869 `Yes` churn labels.
- Duplicate IDs and duplicate full rows: 0. Invalid categories and impossible numeric values: 0. Missing fields outside `TotalCharges`: 0.
- There are 11 blank `TotalCharges` values; all 11 belong to zero-tenure customers and none is churned. Those values alone are set to zero. Rows before/after cleaning: 7,043/7,043.
- Evidence: `data/source_metadata.json`, `outputs/data_quality_report.json`, `outputs/data_quality_report.csv`, and `outputs/cleaned_customers.csv`.

## Machine learning — passed

- Final clean run: training n=5,634; holdout n=1,409; holdout churned n=374; holdout prevalence 26.54%.
- Thresholds came from five-fold OOF training predictions: logistic regression 0.32; XGBoost 0.34.
- Logistic regression: ROC-AUC 0.8417 (bootstrap 95% interval 0.8181–0.8635), average precision 0.6295, precision 0.5302, recall 0.7273, F1 0.6133, accuracy 0.7566, specificity 0.7671, Brier 0.1383. Confusion matrix TN=794, FP=241, FN=102, TP=272.
- XGBoost: ROC-AUC 0.8465 (bootstrap 95% interval 0.8251–0.8681), average precision 0.6603, precision 0.5645, recall 0.7139, F1 0.6305, accuracy 0.7779, specificity 0.8010, Brier 0.1351. Confusion matrix TN=829, FP=206, FN=107, TP=267.
- SHAP validation: passed on the fitted final XGBoost booster; 500 holdout rows and 45 transformed features. Summary, mean-absolute bar, and local waterfall figures were created. SHAP scale is raw model margin (log-odds); attributions are not causal.
- Evidence: `outputs/metrics.json`, `model_comparison.csv`, `confusion_matrix.csv`, `feature_importance_shap.csv`, SHAP PNGs, and `roc_pr_curves.png`.

## PostgreSQL — prior run passed; current rerun unavailable

- The recorded PostgreSQL 16.15 run on 2026-10-20 loaded 7,043 customer rows and 7,043 risk-score rows, executed all 14 named SQL query blocks, and passed all nine Pandas parity comparisons. Internet add-on adoption used the 5,517 customers with internet service as its denominator.
- Evidence: `outputs/postgres_validation.json`. That artifact predates the latest analytics refresh and is retained as historical evidence.
- The database integration could not be rerun during this final validation. The Docker client could not connect to its local Linux engine named pipe, and `TELCO_PG_DSN` was not configured. The latest pytest run therefore skipped the PostgreSQL integration test. Do not treat the historical artifact as validation of the newly regenerated score export.

## Automated tests

| Command | Result |
|---|---|
| Final compile: `python -m compileall -q src scripts tests` | Passed. |
| Final analytics pipeline: `python src\analysis.py` | Passed on the verified raw data; regenerated chart/model outputs and saved scorer. |
| Power BI data preparation: `python scripts\prepare_powerbi.py` | Passed; row, ID, metric, and confusion-count reconciliations matched. |
| Power BI project generation: `python scripts\build_powerbi_project.py` | Passed; six pages, nine tables, and 43 visuals. |
| PBIR validator: `npx --yes --package @microsoft/powerbi-report-authoring-cli@0.5.0 powerbi-report-author validate powerbi\TelecomRetention\TelecomRetention.pbip` | **Passed; 0 errors and 0 warnings.** |
| Automated suite: `python -m pytest -q` | **20 passed, 1 skipped, 0 failed.** The PostgreSQL integration test skipped because `TELCO_PG_DSN` is not configured. |
| PostgreSQL integration | Not rerun; Docker's local Linux engine pipe was unavailable. The successful 2026-10-20 run is documented above. |

The final analytics, Power BI preparation, and automated suite used Python 3.12.14 in the pinned environment from `requirements-lock.txt`. Database credentials are supplied through local environment configuration and are not recorded in this report.

The GitHub Actions workflow is configured with a disposable PostgreSQL 16 service and an integration-only test credential, so CI will exercise the SQL/Pandas parity test instead of taking the local environment's skip path. This workflow has not yet run on the remote repository.

### Failures encountered and resolved

- The first pipeline attempt found a monthly-charge aggregate column-name mismatch. The second found that the installed scikit-learn version did not accept a `color` argument in `RocCurveDisplay.from_predictions`. Both root causes were fixed before the final clean run.
- The earlier PostgreSQL container start found host port 5432 occupied. Compose now binds host port 55432 to loopback and requires a local password; the latest integration rerun was unavailable because Docker's engine pipe could not be reached.
- An earlier post-implementation test run had 12 passes and 4 failures: three fixture tests were intercepted by a project-dataset hash check, and one static Power BI wording assertion did not match the guide. Those causes were fixed. The latest suite reports 20 passed and 1 skipped.
- No executed Python, chart, inference, or PBIR validator checks failed. Current PostgreSQL execution is unverified, as described above.

## Power BI — PBIR validated; Desktop checks not run

- Created a PBIP project at `powerbi/TelecomRetention/TelecomRetention.pbip`, with a six-page PBIR report, nine-table TMDL semantic model, project-root M parameter, custom registered theme, and 28 documented DAX measures.
- Microsoft's `@microsoft/powerbi-report-authoring-cli@0.5.0` validator returned **succeeded: 0 errors, 0 warnings**. The report contains 43 visuals, including four executive-page dropdown slicers. Page metadata and visual summaries are in `powerbi/TelecomRetention/REPORT_PAGES.md` and `powerbi/TelecomRetention/`.
- The reporting data preparation passed independent checks: 7,043 unique customer IDs and exact customer/score alignment; 1,869 churned and 5,174 retained; 1,409 held-out rows; XGBoost ROC-AUC 0.8465008 and average precision 0.6602855 recomputed from the held-out scores; confusion counts total 1,409. Details: `powerbi/data/validation.json` and `powerbi/VALIDATION_REPORT.md`.
- Power BI Desktop 2.159.883.0 is installed. The Microsoft Desktop Bridge CLI launched the `.pbip`, but reported only blank `Untitled - Power BI Desktop` instances with an empty `currentFilePath`. The Desktop preview returned `HOST_UNAVAILABLE` because no report folder was open.
- Desktop semantic-model acceptance, CSV refresh, DAX execution, visual rendering, slicer behavior, screenshot capture, and PBIX save are **not verified**. No genuine report screenshots or PBIX cache are included. The PBIP is schema-valid at the PBIR report layer; it has not been represented as Desktop-opened or visually inspected.

## Runtime versions

The final pipeline version report is `outputs/runtime_versions.json`: Python 3.12.14, NumPy 2.5.4, Pandas 3.0.3, scikit-learn 1.9.1, XGBoost 3.4.1, SHAP 0.54.1, Matplotlib 3.11.2. The full environment is pinned in `requirements-lock.txt`.
