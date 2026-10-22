# Model Card

## Summary

This project compares a logistic-regression baseline with XGBoost for retrospective binary churn classification on the IBM Telco snapshot. XGBoost is the model used for the customer risk-score and SHAP exports because it is the requested tree model for this project; the holdout results do not establish a decisive advantage over logistic regression.

## Data and target

- Dataset: 7,043 rows from the single-snapshot IBM sample.
- Target: `Churn` (`Yes` / `No`), encoded as `Churn_Flag`.
- Predictors exclude `customerID`, `Churn`, `Churn_Flag`, and derived `tenure_band`.
- Split: stratified 80/20 with seed 42; train n=5,634, untouched test n=1,409.
- Test set: 374 positive churn labels; prevalence 26.54%.
- Preprocessing is inside the scikit-learn pipeline and fitted during training folds only.
- Five-fold stratified CV selects hyperparameters on training data. Classification thresholds maximize F1 using training out-of-fold probabilities; test labels are not used for threshold selection.

## Holdout results

| Metric | Logistic regression | XGBoost |
|---|---:|---:|
| Threshold (training OOF) | 0.32 | 0.34 |
| ROC-AUC | 0.8417 | 0.8465 |
| ROC-AUC bootstrap 95% interval | 0.8181–0.8635 | 0.8251–0.8681 |
| Average precision (PR-AUC) | 0.6295 | 0.6603 |
| Precision | 0.5302 | 0.5645 |
| Recall | 0.7273 | 0.7139 |
| F1 | 0.6133 | 0.6305 |
| Accuracy | 0.7566 | 0.7779 |
| Specificity | 0.7671 | 0.8010 |
| Brier score | 0.1383 | 0.1351 |
| Confusion matrix (TN, FP, FN, TP) | 794, 241, 102, 272 | 829, 206, 107, 267 |

The holdout supports useful ranking performance above the 26.54% positive prevalence, but the small ROC-AUC difference and overlapping bootstrap intervals do not prove that one model is superior. No formal paired model comparison was run. Precision/recall depend on a threshold chosen to maximize F1, not on campaign economics.

Machine-readable metrics and parameters are in `outputs/metrics.json`; the long-form metric table is `outputs/model_comparison.csv`.

## Explainability

SHAP was run on the final fitted XGBoost booster for 500 holdout records, after the fitted preprocessor transformed the features. The 45 transformed columns and mean absolute SHAP values are in `outputs/feature_importance_shap.csv`. The summary, bar, and local waterfall figures are under `outputs/`. SHAP values are raw-margin (log-odds) attributions. They describe how this model decomposes predictions and should not be read as causal effects.

## Intended use

Educational analysis and decision-support prototype for evaluating a possible prioritization workflow. Any future queue should be evaluated on current active customers using a later-period test and a contact-capacity/cost policy.

## Not intended for

- Automatic customer decisions or denial of service.
- Claims that a high score means a customer will definitely churn.
- Estimating retention campaign effectiveness, customer lifetime value, profit, or savings.
- Production use without temporal validation, calibration review, monitoring, and intervention experiments.

## Limitations and risks

- A random holdout from one historical snapshot cannot establish performance on future periods or changing products/prices.
- Observed associations may reflect confounding, measurement choices, or customer selection.
- The F1 threshold does not encode costs of false positives, false negatives, contact capacity, or offer value.
- The sample has no campaign assignment, offer acceptance, customer contact history, margins, or intervention outcomes.
- Training OOF and holdout scores use different prediction procedures; the `data_split` field must remain in downstream analysis.
