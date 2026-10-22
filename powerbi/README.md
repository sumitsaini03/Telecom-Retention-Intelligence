# Telecom Retention Intelligence — Power BI

This folder contains a real Power BI Project (`.pbip`), its PBIR report definition, a TMDL semantic model, typed Power Query imports, DAX measures, a custom theme, and reproducible data-preparation scripts.

## Open the report

Open [TelecomRetention.pbip](TelecomRetention/TelecomRetention.pbip) in Power BI Desktop. The report folder and semantic-model folder must remain beside the `.pbip` file. The report imports local CSVs from `powerbi/data/` through the `ProjectRoot` Power Query parameter.

The project was generated with the current repository root as its parameter value. On a different checkout, run the build commands below; `build_powerbi_project.py` rewrites `ProjectRoot` to the location of that checkout. If you edit the path manually, update `ProjectRoot` in `TelecomRetention/TelecomRetention.SemanticModel/definition/expressions.tmdl` and save the project.

## Regenerate and refresh data

Run these commands from the repository root in Windows PowerShell after installing the project dependencies described in the root README:

```powershell
python src/analysis.py
python scripts/prepare_powerbi.py
python scripts/build_powerbi_project.py
```

The first command regenerates the authoritative cleaning, scoring, and evaluation outputs. The second validates and exports Power BI import tables to `powerbi/data/`. The third creates the PBIP's TMDL tables, M queries, DAX measure definitions, PBIR visuals, and theme registration. Open the `.pbip` and choose **Home → Refresh** in Power BI Desktop after the CSVs change.

`prepare_powerbi.py` does not retrain a separate model. It consumes the existing pipeline outputs and verifies the score-to-customer join, probability bounds, held-out metrics, and confusion-matrix total. ROC and precision-recall metrics are computed from the actual XGBoost test scores and labels. The full threshold-level points are retained; duplicate x-values are reduced to the maximum y-value only in the two line-chart plotting tables so Power BI can use a numeric x-axis without grouping duplicate categories.

## Report pages

| Page | What it answers | Main contents |
|---|---|---|
| Executive Overview | How large is the observed churn problem, and where should a manager start? | Six KPI cards; churn mix; contract, tenure, and internet-service comparisons; four dropdown slicers for contract, tenure band, internet service, and payment method; evidence-backed investigation table. |
| Understanding Churn Drivers | Which observed groups have higher churn rates? | Churn-rate comparisons by contract, tenure, payment method, internet service, monthly-charge band, and technical support; recommendation evidence and validation notes. |
| Customer Segments & Exposure | How do customer mix and observed charges vary across segments? | Phone/internet combinations; churned customers by monthly-charge band; observed charges by churn status; tenure/charge pattern; contract summary; caveats about financial interpretation. |
| Retention Opportunities | How do model scores line up with outcomes in the held-out evaluation? | Test-set counts by risk tier, observed churn by tier, predicted probabilities, high-risk segment counts, and evidence-backed investigation ideas. This is retrospective evaluation, not a current campaign list. |
| Model Performance & Reliability | How did the models perform on unseen test rows? | Logistic regression and XGBoost comparison; confusion-matrix cells; ROC and precision-recall curves from held-out scores; probability by outcome; top 10 mean-absolute SHAP features. |
| Retention Action Plan | What should a team investigate and validate next? | Findings, evidence, hypotheses, priorities, validation steps, and the scenario's explicit assumptions. |

All charts and slicers use built-in Power BI visuals; chart selections cross-filter other visuals on that page. The overview dropdown slicers filter that page's customer-profile visuals. Model-evaluation artifacts are intentionally disconnected from the customer snapshot and remain fixed to the held-out split. Slicers do not synchronize across pages.

## Data model and interpretation

The semantic model imports nine CSV tables: `Customer Profile`, `Holdout Scores`, `Model Metrics`, `Confusion Matrix`, `ROC Curve`, `Precision Recall Curve`, `Feature Importance`, `Retention Scenario`, and `Recommendations`. The tables are intentionally disconnected. Customer attributes describe all 7,043 rows; model metrics, confusion counts, and curves describe a fixed 1,409-row test split. A relationship could make a test metric appear to be recomputed for a filtered segment, which it is not.

`Customer Profile` uses the cleaned source columns plus the existing risk-score export and derived `MonthlyChargeBand`, `ServiceCombination`, tenure-band sort order, and risk-tier sort order. `Holdout Scores` contains only the 1,409 final test rows. `ProjectRoot` is the one local-path parameter. The actual M files imported by the model are under `TelecomRetention/PowerQuery/`; this is the single M source directory used by the generated semantic model.

The DAX library is in [`dax/retention_measures.dax`](dax/retention_measures.dax) and is embedded as measures in the TMDL `Customer Profile` table. Customer counts, churn counts, rates, and averages respond to customer-table filters. Model metrics are fixed values from the authoritative evaluation outputs. `MonthlyCharges` has no declared currency code in the source, so the report calls it “source units.” Charges associated with churn-labeled customers are descriptive exposure, not proven lost revenue. SHAP values are raw-margin model associations, not causes. The scenario uses 5%, 10%, and 15% hypothetical effectiveness, an analyst-supplied contact-cost input of 50 in unspecified numeric units per contact, and six assumed months; it is not measured retention, savings, profit, or causal impact.

See [`DATA_DICTIONARY.md`](DATA_DICTIONARY.md) for table fields and derived bins, [`REPORT_PAGES.md`](TelecomRetention/REPORT_PAGES.md) for page interpretations, and [`RECRUITER_DEMO.md`](TelecomRetention/RECRUITER_DEMO.md) for a short walkthrough.

## Check the source project

PBIR report files can be checked with Microsoft's pinned report-authoring CLI. Node.js/npm are needed only for this check, not for viewing a saved report:

```powershell
npx --yes --package @microsoft/powerbi-report-authoring-cli@0.5.0 powerbi-report-author validate powerbi\TelecomRetention\TelecomRetention.pbip
```

The semantic model imports local project CSVs when Power BI Desktop opens and refreshes it. In this environment, the PBIR structure was validated, but Desktop did not report the PBIP folder as open; a Desktop refresh, visual/DAX verification, and genuine screenshots are therefore not claimed. Details and exact reconciliation values are in [`VALIDATION_REPORT.md`](VALIDATION_REPORT.md).
