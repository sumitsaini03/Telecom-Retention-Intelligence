# Business Insights

All rates below are observed proportions in the IBM snapshot. Segment percentages use the segment's customer count as the denominator. These associations are descriptive and do not establish what caused churn.

## Observed customer patterns

- **Contract:** Month-to-month customers had 1,655 churn labels among 3,875 customers (42.7%). The one-year group was 166/1,473 (11.3%); the two-year group was 48/1,695 (2.8%). Source: `outputs/business_aggregates.csv`, `outputs/postgres_validation.json` (`churn_by_contract`).
- **Tenure:** 0–12 month customers had 1,037/2,186 churn (47.4%); the 49–72 month group had 213/2,239 (9.5%). Source: `outputs/business_aggregates.csv`, SQL/Pandas parity check `churn_by_tenure_band`.
- **Internet service:** Fiber optic had 1,297/3,096 churn (41.9%), DSL 459/2,421 (19.0%), and no internet service 113/1,526 (7.4%). Source: `outputs/business_aggregates.csv` and `outputs/postgres_validation.json` (`churn_by_internet_service`).
- **Payment:** Electronic check had 1,071/2,365 churn (45.3%), versus 232/1,522 (15.2%) for automatic credit card. Source: `outputs/business_aggregates.csv` and `outputs/postgres_validation.json` (`churn_by_payment_method`).
- **Support and billing:** Customers with no technical support had 1,446/3,473 churn (41.6%); customers with support had 310/2,044 (15.2%). Paperless billing customers had 1,400/4,171 churn (33.6%), versus 469/2,872 (16.3%) for non-paperless billing. Source: `outputs/business_aggregates.csv`.
- **Internet add-ons:** The add-on count analysis uses only 5,517 customers with internet service. Churn was 718/1,267 (56.7%) at zero qualifying add-ons and 25/470 (5.3%) at four. The intermediate groups were 570/1,467 (38.9%), 326/1,372 (23.8%), and 117/941 (12.4%). Source: `outputs/addon_adoption.csv`; the SQL uses and parity-checks the same internet-only denominator. This gradient may reflect customer, service, or tenure differences; it is not evidence that selling add-ons prevents churn.
- **Monthly charges:** Average charges were 74.44 source units for churn-labeled customers (n=1,869) and 61.27 source units for non-churned customers (n=5,174). The source does not name a currency. Source: `outputs/postgres_validation.json` (`average_charges_by_churn`). These are descriptive differences.

Overall, 1,869 of 7,043 customers are marked churned (26.54%); the dataset average tenure is 32.37 months and average monthly charge is 64.76 source units. Source: `outputs/data_quality_report.json` and `outputs/postgres_validation.json` (`overall_churn`).

## Holdout model results

The untouched holdout contained 1,409 customers and 374 churn labels (26.54% prevalence). Logistic regression achieved ROC-AUC 0.8417 and average precision 0.6295 at a training-OOF-selected threshold of 0.32. XGBoost achieved ROC-AUC 0.8465 and average precision 0.6603 at threshold 0.34. XGBoost's measured improvement was modest; the bootstrap ROC-AUC intervals overlap. No formal test of the difference was performed. Source: `outputs/metrics.json` and `outputs/model_comparison.csv`.

## Model associations

The largest mean absolute TreeSHAP values for the fitted XGBoost model were for the month-to-month contract indicator, tenure, monthly charges, online security, and fiber-optic internet. Source: `outputs/feature_importance_shap.csv`. These values explain model output on the raw margin scale, not customer behavior or causal mechanisms.

## How the analysis could support a workflow

The scores can be used to define a retrospective prioritization queue for review, with the test rows clearly separated from training OOF rows. A real deployment would require time-based validation on later customers, a score cutoff tied to contact capacity and intervention cost, and an experiment that compares offer outcomes to a control group. The current dataset does not say which customers accept offers or whether an offer prevents churn.

## Scenario arithmetic

The highest observed churned-monthly-charge segment with at least 50 customers was Month-to-month / Fiber optic / Electronic check: 1,307 customers, 789 churned (60.4%), and average monthly charges of 87.18 source units. Under a purely hypothetical 5% effectiveness assumption, the table computes 39.45 customers hypothetically retained and 20,636.20 source-unit charges over six assumed months, against 65,350 assumed contact-cost units at 50 per contact for each of 1,307 customers. Source: `outputs/retention_scenario.csv` and `outputs/retention_scenario_inputs.json`. These are not observed outcomes, profit, savings, or a campaign forecast. The cost and charge values are assumptions/arithmetic in the dataset's unspecified numeric units; margin, actual offer cost, selection, and causal effect are unavailable.
