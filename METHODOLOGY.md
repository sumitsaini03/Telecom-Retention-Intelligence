# Methodology

## Data preparation

`src/analysis.py` validates the IBM CSV schema, category domains, identifier uniqueness, numeric ranges, missing values, and row accounting. The raw file is preserved. `TotalCharges` is parsed as numeric; only the 11 verified blanks for zero-tenure, non-churn customers are set to zero. A separate cleaned table is exported.

Observed churn rates use each segment's customer count as the denominator. The add-on count analysis includes internet-service customers only. Counts, averages, observed labels, model scores, and hypothetical scenario values are exported separately so they are not conflated.

## Model design

- Target: `Churn_Flag`; excluded from all model features along with `Churn`, `customerID`, and the derived `tenure_band`.
- Split: 80% training / 20% untouched holdout, stratified by the target, seed 42.
- Preprocessing: median imputation and standard scaling for numeric columns; most-frequent imputation and one-hot encoding for categoricals. A scikit-learn `Pipeline` and `ColumnTransformer` fit preprocessing within each training fold.
- Models: logistic regression baseline and XGBoost classifier.
- Model selection: five-fold stratified cross-validation on training data, optimizing ROC-AUC. Hyperparameter searches and all preprocessing are confined to training data.
- Threshold: the F1-maximizing threshold is selected from five-fold out-of-fold training probabilities. Holdout labels are not used to tune it.
- Evaluation: the chosen pipelines are evaluated once on the holdout. ROC-AUC, average precision, precision, recall, F1, accuracy, specificity, Brier score, confusion matrix, holdout size, and positive prevalence are saved. A percentile bootstrap interval describes holdout ROC-AUC uncertainty.

The threshold's OOF probabilities use hyperparameters selected by cross-validation on the training partition. This is valid with respect to the untouched test set; a nested-CV design would provide a less selection-optimistic threshold estimate if the threshold itself were a research endpoint.

## Explainability

TreeSHAP is computed from the fitted XGBoost booster using the transformed holdout feature matrix and transformed feature names. The summary, mean-absolute-importance, and local waterfall plots are produced by the same run. The local row is the highest predicted-risk row in the explained holdout sample. XGBoost explanations are on raw margin (log-odds) scale and describe the model's associations, not causal drivers.

## Prediction provenance

`customer_risk_scores.csv` contains one row per source customer. Training rows receive out-of-fold probabilities and are labeled `train_oof`; holdout rows receive predictions from the final training-fitted model and are labeled `test`. The two populations are not interchangeable. Holdout evaluation metrics use only `data_split = test`.

## Business scenario

The scenario selects a historical segment using observed churned monthly charges among segments with at least 50 records. It applies explicit hypothetical intervention effectiveness, contact cost, and duration assumptions. Outputs are arithmetic illustrations in gross billed charges; they are not profit, proven savings, an offer response prediction, or causal impact. An adequately powered randomized campaign experiment plus margin and contact-cost data would be required to estimate impact.
