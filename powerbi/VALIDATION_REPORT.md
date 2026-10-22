# Power BI validation report

Run date: 2026-10-22 (Asia/Calcutta)

## Data and model reconciliation — passed

`python scripts/prepare_powerbi.py` read the existing project outputs and wrote the Power BI import layer. Its result is preserved in [`data/validation.json`](data/validation.json).

- 7,043 cleaned customers; 7,043 unique customer IDs; the customer-to-score ID sets match exactly.
- Observed churn: 1,869; retained: 5,174; churn rate: 26.536987%.
- Mean tenure: 32.3711 months; mean `MonthlyCharges`: 64.7617 source numeric units.
- Final held-out test split: 1,409 customers, including 374 churn labels; predicted probabilities were within [0.005669, 0.907198].
- XGBoost ROC-AUC recomputed from the joined test rows: 0.8465008138, matching the authoritative metric. Average precision: 0.6602854977, also matching.
- Confusion-matrix cell counts sum to 1,409. The original customer/risk-score join preserves all 7,043 customer rows.
- The exact score-threshold curve tables contain 421 ROC and 1,356 precision-recall points. Plot-ready tables collapse repeated x coordinates to the maximum y at each x; model metrics still use all test scores.

## PBIR structure — passed

Microsoft's `@microsoft/powerbi-report-authoring-cli@0.5.0` validated `TelecomRetention.pbip` with **0 errors and 0 warnings**. Its page catalog found six pages, and its visual catalog found 43 visuals including four executive dropdown slicers. The validator checked PBIR JSON schemas, visual role bindings, report pages, layout, and registered theme. The custom theme is included in `TelecomRetention.Report/StaticResources/RegisteredResources/`.

The project contains a TMDL semantic model with nine CSV-backed tables, a `ProjectRoot` M parameter, 28 described DAX measures, and the report's PBIR definitions. The model has no relationships by design: all-customer customer-profile analyses and fixed held-out model-evaluation tables stay separate, so evaluation metrics cannot be mistaken for segment-specific recomputations.

The Power BI handoff checks are included in the latest 20-pass test suite. They cover the PBIP artifact, six-page metadata, actual Power Query M/TMDL sources, and DAX measure definitions; they are not a substitute for Desktop execution.

## Desktop acceptance — not verified

Power BI Desktop 2.159.883.0 is installed at `C:\Program Files\WindowsApps\Microsoft.MicrosoftPowerBIDesktop_2.159.883.0_x64__8wekyb3d8bbwe\bin\PBIDesktop.exe`. The Microsoft Desktop Bridge CLI launched the `.pbip`, but its status continued to show blank `Untitled - Power BI Desktop` instances with `currentFilePath` empty and no report pages. A Desktop preview consequently returned `HOST_UNAVAILABLE` because no instance had the report folder open. Opening `definition.pbir` directly also did not produce a bridge instance with the report loaded.

Therefore this environment did not verify semantic-model acceptance by Desktop, Power Query execution/refresh, DAX execution, visual layout/interactions, or report screenshots. No `.pbix` cache is included. The `.pbip` is a generated PBIR/TMDL project with zero PBIR schema errors; it is not represented as Desktop-opened or visually inspected.

## How to complete Desktop checks

1. Run the three generation commands in [`README.md`](README.md), especially `python scripts/build_powerbi_project.py` after cloning so `ProjectRoot` is local.
2. Open `TelecomRetention/TelecomRetention.pbip` in Power BI Desktop and refresh.
3. Check that all nine queries load. Verify 7,043 customer rows, 1,869 churned rows, and 26.54% observed churn.
4. Check the held-out model table against `data/ModelMetrics.csv` and `data/ConfusionMatrix.csv` (n=1,409; XGBoost ROC-AUC 0.8465; average precision 0.6603).
5. Exercise the four overview slicers and verify same-page visuals recalculate. Confirm model evaluation pages remain fixed to the held-out export.
6. Capture actual screenshots of all six report pages and add them under `TelecomRetention/screenshots/` if desired.

No screenshot paths are listed because no genuine Desktop report screenshots were captured in this run.
