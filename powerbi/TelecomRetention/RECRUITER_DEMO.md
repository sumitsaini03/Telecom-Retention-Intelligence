# Recruiter demonstration guide

## Suggested 4–5 minute walkthrough

### 1. Executive Overview

Start with the customer base and observed churn KPIs. The project contains 7,043 customers, of whom 1,869 (26.54%) are labeled churned. Show how the contract, tenure, internet-service, and outcome visuals respond to the four dropdown slicers. The overview calls out observed patterns for investigation; it does not claim that any field causes churn.

### 2. Understanding Churn Drivers

Compare churn rate with segment size. Month-to-month customers show 1,655 churn labels among 3,875 customers (42.7%); customers in the first 12 months show 1,037 among 2,186 (47.4%). Electronic-check customers are 1,071/2,365 (45.3%), and fiber-optic customers are 1,297/3,096 (41.9%). These are descriptive differences in one historical snapshot. A retention team should investigate onboarding, billing, and service experience before proposing an intervention.

### 3. Customer Segments & Exposure

Point out the contract summary and how observed monthly charges vary by churn label. Explain that `MonthlyCharges` has no currency code in the source. The monthly charges associated with churn-labeled rows are a descriptive exposure measure; the dataset has no future billing, margin, or realized-loss outcome.

### 4. Retention Opportunities

This page uses only the 1,409-row test split for retrospective model review. It compares risk tiers with actual held-out outcomes, not a live retention queue. A churn model helps prioritize review but does not estimate whether an offer will change a customer's outcome. Do not interpret false positives as customers who would have been saved.

### 5. Model Performance & Reliability

On the fixed holdout, XGBoost ROC-AUC is 0.8465 and average precision is 0.6603; precision is 0.5645, recall 0.7139, F1 0.6305, and the threshold is 0.34. The comparison table includes the logistic-regression baseline on the same holdout. The threshold was selected from five-fold out-of-fold training predictions. Explain the confusion matrix and precision/recall trade-off; neither metric set chooses an economically optimal campaign policy. The SHAP ranking is raw-margin evidence about this fitted model, not causal evidence.

### 6. Retention Action Plan

Finish with the evidence-backed investigation recommendations and validation steps. The displayed scenario uses hypothetical 5%, 10%, and 15% effectiveness, an analyst-supplied contact-cost input of 50 in unspecified numeric units, and six retained months. Its arithmetic is illustrative only; no experiment measured retention effectiveness, savings, revenue, or profit.

## Resume bullet alternatives

- Built a six-page Power BI Project (PBIP) for telecom churn reporting with 43 report visuals, four dropdown slicers, nine typed Power Query import tables, a TMDL semantic model, and a documented DAX measure library; verified the PBIR schema and reconciled 7,043 customer rows to the source analytics.
- Connected a reproducible Python churn pipeline to Power BI, importing observed customer profiles separately from the fixed 1,409-row test evaluation; independently reconciled XGBoost ROC-AUC (0.8465), average precision (0.6603), and confusion-matrix totals.
- Translated churn analysis into six management-oriented report pages, showing a 26.54% observed churn rate and descriptive segment differences while labeling monthly-charge exposure, SHAP attribution, and retention-scenario outputs with their limitations.

The PBIR schema and source data were validated. Power BI Desktop opening, refresh, DAX execution, final page rendering, and genuine screenshots were not verified in this environment; describe those checks accordingly in an interview.
