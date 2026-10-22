# Power BI data dictionary

## Source and transformation

The verified source is the IBM Telco Customer Churn sample (7,043 customer rows). The Power BI preparation pipeline reads the cleaned customer table and the existing customer-risk, metric, confusion-matrix, SHAP, and scenario outputs. It joins customer records to prediction records by unique `customerID`; it fails if IDs are missing, duplicated, or misaligned. It does not make up model scores.

`Customer Profile` retains the source profile fields: `customerID`, `gender`, `SeniorCitizen`, `Partner`, `Dependents`, `tenure`, `PhoneService`, `MultipleLines`, `InternetService`, `OnlineSecurity`, `OnlineBackup`, `DeviceProtection`, `TechSupport`, `StreamingTV`, `StreamingMovies`, `Contract`, `PaperlessBilling`, `PaymentMethod`, `MonthlyCharges`, `TotalCharges`, and `Churn`. Existing pipeline fields `Churn_Flag` and `tenure_band` are retained. The score join adds `churn_probability`, `predicted_churn`, `risk_tier`, `model_identifier`, and `data_split`.

Derived customer fields:

| Field | Definition |
|---|---|
| `MonthlyChargeBand` | `0 to <30`, `30 to <60`, `60 to <90`, or `90+`, using the source numeric `MonthlyCharges` value. These are descriptive bins. |
| `ServiceCombination` | `Phone` or `No phone`, paired with `DSL`, `Fiber optic`, or `No internet`. |
| `tenure_band_order` | Numeric sort key parsed from the existing `tenure_band` label so categories display in tenure order. |
| `risk_tier_order` | Sort key for the existing score export: Low (1), Medium (2), High (3), Critical (4). |

`TotalCharges` blanks were already handled by the source cleaning pipeline; its 11 zero-tenure, non-churn rows are set to 0. No customer rows are removed.

## Imported tables

| Model table | File | Rows | Purpose |
|---|---|---:|---|
| `Customer Profile` | `CustomerReport.csv` | 7,043 | All-customer observed outcomes, profiles, charges, and provenance-labeled model scores. |
| `Holdout Scores` | `HoldoutScores.csv` | 1,409 | Final test split only; contains observed label, XGBoost score, risk tier, and selected customer attributes. |
| `Model Metrics` | `ModelMetrics.csv` | 2 | Logistic regression and XGBoost metrics on the same final holdout. Thresholds came from training OOF predictions. |
| `Confusion Matrix` | `ConfusionMatrix.csv` | 8 | Actual/predicted outcome cell counts for both models at their respective thresholds. |
| `ROC Curve` | `ROCCurvePlot.csv` | 228 | Plot-ready XGBoost held-out ROC points. Exact threshold-level curve is in `ROCCurve.csv` (421 points). |
| `Precision Recall Curve` | `PrecisionRecallCurvePlot.csv` | 362 | Plot-ready held-out precision/recall points. Exact threshold-level curve is in `PrecisionRecallCurve.csv` (1,356 points). |
| `Feature Importance` | `FeatureImportanceTop10.csv` | 10 | Top mean-absolute TreeSHAP features from the fitted XGBoost model, in raw-margin units. |
| `Retention Scenario` | `RetentionScenario.csv` | 3 | Three explicitly hypothetical effectiveness assumptions for the same observed segment. |
| `Recommendations` | `Recommendations.csv` | 4 | Evidence-backed observed patterns plus follow-up actions and validation notes. |

The three scenario rows use effectiveness assumptions of 5%, 10%, and 15%; the scenario's analyst-supplied contact-cost input is 50 in unspecified numeric units per contacted customer, and retained duration is assumed to be six months. `customers_retained_hypothetical` can be fractional because it is arithmetic, not a count of observed saved customers.

## Core measure definitions

| Measure | Definition |
|---|---|
| Total Customers | Distinct customer IDs after current `Customer Profile` filters. |
| Churned Customers | Distinct IDs where `Churn = "Yes"`. |
| Retained Customers | Total minus churned customers. |
| Observed Churn Rate | Churned customers / total customers in current filter context. |
| Average Tenure Months | Arithmetic mean of source `tenure`. |
| Average Monthly Charges | Mean `MonthlyCharges`; the source numeric unit is not assigned a currency code. |
| Monthly Charges Associated with Churned Customers | Sum of `MonthlyCharges` for rows labeled churned; descriptive exposure only. |
| Holdout Observed Churn Rate | Churn-labeled held-out rows / selected held-out rows. |
| Holdout High Risk Customers | Held-out rows in the existing High or Critical risk tiers. |
| XGBoost ROC-AUC / Average Precision / Precision / Recall / F1 / Accuracy / Threshold | Fixed held-out output values; they are not re-estimated by report filters. |

The complete DAX source includes descriptions, formats, and display folders: [`dax/retention_measures.dax`](dax/retention_measures.dax). The Python reconciliation source is [`../scripts/prepare_powerbi.py`](../scripts/prepare_powerbi.py).
