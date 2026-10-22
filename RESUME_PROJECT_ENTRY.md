# Resume Project Entry

## Project title

**Telecom Retention Intelligence — Churn Analytics and Risk Prioritization**

## One-line summary

Built a reproducible churn analytics and model-evaluation pipeline on the public IBM Telco sample, with validated data cleaning, PostgreSQL analysis, XGBoost/SHAP interpretation, and a six-page Power BI Project report.

## Resume bullets

- Validated and cleaned the authentic 7,043-row, 21-column IBM Telco dataset; verified the source SHA-256, retained all rows, and converted only 11 blank `TotalCharges` entries confirmed to belong to zero-tenure non-churn customers.
- Compared logistic regression and XGBoost with training-only preprocessing, five-fold cross-validation, and out-of-fold threshold selection; XGBoost achieved 0.8465 ROC-AUC and 0.6603 average precision on a 1,409-customer holdout (threshold 0.34).
- Executed 14 PostgreSQL business analyses on PostgreSQL 16 and reconciled nine required aggregates with independent Pandas calculations, including the internet-only add-on denominator; built a six-page PBIP/TMDL report and validated its PBIR schema and Power BI import-table reconciliations.

## Technology stack

Python 3.12, Pandas, NumPy, scikit-learn, XGBoost, SHAP, Matplotlib, PostgreSQL 16, psycopg, Power BI PBIP/PBIR/TMDL, Power Query M, DAX, pytest, Docker Compose.

## Internship interview explanation

I started with IBM's public telecom churn sample and made the data quality checks explicit before modeling. The pipeline preserves the source, validates its schema and values, and only imputes the 11 blank total-charge values after checking that all 11 customers had zero tenure and no churn label. I compare a logistic regression baseline with XGBoost using a stratified holdout, training-only cross-validation, and a threshold chosen from out-of-fold training predictions. On the holdout, both models ranked churn risk reasonably well; the XGBoost ROC-AUC was 0.8465 and average precision was 0.6603, but the difference from logistic regression is modest and not proof of a decisive model advantage. I also ran 14 PostgreSQL analyses and checked their counts and rates against Pandas. SHAP helps describe what the fitted XGBoost model used, while the scenario is explicitly hypothetical because this dataset contains no retention experiment. I created a six-page PBIP report with a TMDL model and typed Power Query imports; its PBIR schemas and report-data reconciliations passed. Desktop refresh and screenshots were not verified in this environment.

## Likely technical interview questions

### 1. How did you prevent target and identifier leakage?

`customerID`, `Churn`, and `Churn_Flag` are excluded before fitting. The derived tenure band is also excluded because raw tenure is already a feature. Preprocessing sits inside the model pipeline and is fitted within training folds.

### 2. How did you select the classification threshold?

The threshold maximizes F1 over a fixed candidate grid using five-fold out-of-fold probabilities from the training partition. The holdout labels are used only for final evaluation. The threshold is not economically optimized; contact costs and intervention outcomes are absent.

### 3. Why report average precision as well as ROC-AUC?

The positive class is 26.54% of the dataset. Average precision summarizes precision/recall trade-offs for the churn class and is useful when a team cares about how many contacted customers are relevant. ROC-AUC measures ranking across thresholds. Neither metric chooses a business policy by itself.

### 4. Did XGBoost clearly beat logistic regression?

Not conclusively. On this holdout, XGBoost ROC-AUC was 0.8465 versus 0.8417, and average precision was 0.6603 versus 0.6295. The ROC-AUC bootstrap intervals overlap and no paired significance test was run, so I describe the measured difference without claiming a decisive winner.

### 5. What do the SHAP values mean here?

TreeSHAP attributes raw-margin (log-odds) model output across 45 transformed features for 500 holdout rows. A large attribution means that feature contributed strongly to this model's prediction. It does not show that changing the feature would change churn.

## Limitations and design decisions to defend

1. The data is a single observational snapshot, so a random holdout does not test future-period generalization. A deployment would need temporal validation and monitoring.
2. The threshold maximizes F1 rather than expected business value. A real policy needs contact capacity, offer cost, margin, and error-cost inputs.
3. XGBoost is used for the risk-score/SHAP workflow by project design, not because the holdout proves it is superior. No controlled campaign data exists. The PBIP source project passes PBIR validation, but opening, refresh, DAX execution, and rendering in Desktop were not verified.
