# Data Card

## Dataset

- **Name:** IBM Telco Customer Churn sample
- **Source:** [IBM repository](https://github.com/IBM/telco-customer-churn-on-icp4d) and [raw CSV](https://raw.githubusercontent.com/IBM/telco-customer-churn-on-icp4d/master/data/Telco-Customer-Churn.csv)
- **Upstream code-pattern license:** Apache-2.0, as stated by the IBM repository's `LICENSE` and README.
- **Dataset license:** Not independently established by the upstream materials reviewed. IBM's open [issue #22](https://github.com/IBM/telco-customer-churn-on-icp4d/issues/22) asks whether the data itself is Apache-licensed and has no maintainer answer. Do not treat the code-pattern license as proof of dataset rights; verify the data terms before redistribution outside this educational project.
- **Retrieved and verified:** 2026-10-20; HTTP 200; final URL recorded in `data/source_metadata.json`.
- **Bytes:** 970,457
- **SHA-256:** `16320c9c1ec72448db59aa0a26a0b95401046bef5d02fd3aeb906448e3055e91`
- **Shape:** 7,043 records x 21 source columns.

## Population and intended use

Each row represents one customer in a single snapshot. The data is intended for educational churn analysis, exploratory segmentation, and retrospective binary classification. It does not contain randomized intervention outcomes or a time series suitable for causal or survival analysis.

The target is `Churn` (`Yes`/`No`). `customerID` is retained for joining and prediction provenance but is excluded from predictive features. No names, addresses, phone numbers, or other direct contact information are included in this sample.

## Quality checks

The verified source has 7,043 unique customer identifiers, no duplicate IDs, and churn labels of 5,174 `No` and 1,869 `Yes`. There are 11 blank `TotalCharges` entries. All 11 have tenure zero and none is marked churned, so the cleaning step replaces only those blanks with zero. The raw CSV remains unchanged. All other required fields and categories are validated, and the row count remains 7,043 after cleaning.

The machine-readable evidence is in `outputs/data_quality_report.json` and `.csv`; the cleaned table is `outputs/cleaned_customers.csv`.

## Known limitations

- Single historical snapshot; no event dates, acquisition cohort, or time-aware validation.
- The target reflects the source sample's churn label definition and observation window, which are not fully documented by a data dictionary in the upstream project.
- The source repository is public and archived, but the dataset's separate license remains unresolved in its issue tracker.
- Segment differences and SHAP values are descriptive/model associations. They do not show why customers churn or what an offer would change.
- Customer identifiers are sample IDs and should not be treated as real contactable customers.
- The four-service add-on analysis covers security, backup, device protection, and technical support; it excludes streaming from that specific count. Separate adoption rates cover the six internet add-ons/services.
