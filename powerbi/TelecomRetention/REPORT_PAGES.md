# Report page definitions

1. **Executive Overview** — source-snapshot KPIs, churn mix, contract/tenure patterns, customer counts and evidence-backed investigation priorities.
2. **Understanding Churn Drivers** — observed rate comparisons by contract, tenure, payment, internet, charge band and support; these are associations, not causes.
3. **Customer Segments & Exposure** — customer mix, observed charges grouped by churn status, phone/internet combinations, tenure/charge patterns and contract summary. Charges are source numeric units, not realized lost revenue.
4. **Retention Opportunities** — risk tiers and outcome rates from the fixed held-out test split. It is retrospective evaluation, not a live customer campaign list.
5. **Model Performance & Reliability** — fixed holdout model comparison, confusion counts, ROC/precision-recall plots from actual scores, predicted probabilities and top mean-absolute SHAP features. SHAP values are raw-margin associations, not causes.
6. **Retention Action Plan** — evidence, investigation actions, validation needs and the explicitly hypothetical scenario arithmetic.

All customer-profile measures recalculate with visual cross-filtering. Model evaluation tables and curve points are fixed outputs from the held-out split and are not recomputed by report filters.
