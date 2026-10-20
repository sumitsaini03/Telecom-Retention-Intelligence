# Power BI Build Guide — Telecom Retention Intelligence

> **Status**: This is a *handoff document*. No PBIX file is included because
> Power BI Desktop cannot run in the development environment (Linux sandbox).
> Build the report manually using these instructions.

---

## Prerequisites

| Item | Details |
|------|---------|
| Power BI Desktop | Latest version (June 2024+) |
| Data source | `outputs/customer_risk_scores.csv` |
| Theme | `powerbi/theme.json` (apply via View → Themes → Browse) |
| Supplementary | `outputs/retention_scenario.csv` |

---

## Data Import

1. **Get Data → Text/CSV** → select `outputs/customer_risk_scores.csv`
2. In Power Query:
   - Confirm `churn_probability` is **Decimal Number**
   - Confirm `split` is **Text**
   - Confirm `risk_tier` is **Text**
   - Confirm `Churn` is **Text**
3. **Get Data → Text/CSV** → select `outputs/retention_scenario.csv`
4. Close & Apply.

---

## DAX Measures

Create these measures in a `_Measures` table (Enter Data → empty table → rename):

```dax
// Core counts
Total Customers = COUNTROWS('customer_risk_scores')

Churned Customers =
    CALCULATE(
        COUNTROWS('customer_risk_scores'),
        'customer_risk_scores'[Churn] = "Yes"
    )

Active Customers =
    CALCULATE(
        COUNTROWS('customer_risk_scores'),
        'customer_risk_scores'[Churn] = "No"
    )

Churn Rate =
    DIVIDE([Churned Customers], [Total Customers], 0)

// Risk distribution
High Risk Count =
    CALCULATE(
        COUNTROWS('customer_risk_scores'),
        'customer_risk_scores'[risk_tier] IN {"Critical", "High"}
    )

Avg Churn Probability =
    AVERAGE('customer_risk_scores'[churn_probability])

// For card visuals
Churn Rate Display =
    FORMAT([Churn Rate], "0.0%")
```

---

## Page 1: Churn Overview

| Visual | Source | Position |
|--------|--------|----------|
| Card: Total Customers | `[Total Customers]` | Top-left |
| Card: Churn Rate | `[Churn Rate Display]` | Top-center |
| Card: Churned Customers | `[Churned Customers]` | Top-right |
| Donut: Churn split | `Churn` by `Total Customers` | Center-left |
| Bar: Risk tier distribution | `risk_tier` by `Count of customerID` | Center-right |
| Histogram: Churn probability | `churn_probability` bins | Bottom |

### Slicers (rounded pill style)
- `split` (train_oof / test) — for data provenance transparency
- `Churn` (Yes / No)

---

## Page 2: Active Customer Risk (Default: Churn = No)

> **IMPORTANT**: Set a page-level filter: `Churn` = "No".
> This ensures the dashboard defaults to active customers only,
> since churned customers cannot be retained.

| Visual | Source | Position |
|--------|--------|----------|
| Card: Active Customers | `[Active Customers]` | Top-left |
| Card: High Risk Count | `[High Risk Count]` | Top-center |
| Card: Avg Probability | `[Avg Churn Probability]` | Top-right |
| Bar: Risk tier (active only) | `risk_tier` by count | Center-left |
| Table: Top at-risk customers | `customerID`, `churn_probability`, `risk_tier` | Center-right, sorted desc |
| Retention scenario | Import from `retention_scenario.csv` as reference table | Bottom |

### Cross-filtering
- Clicking a bar in the risk-tier chart filters the customer table.

---

## Theme Application

1. View → Themes → Browse for themes
2. Select `powerbi/theme.json`
3. Font: **Segoe UI** throughout
4. Accent: Navy `#2b6cb0`, churn red `#c53030`, neutral grey `#718096`
5. Background: White `#ffffff`

---

## Validation Checklist

After building the report, verify these values against `outputs/metrics.json`:

- [ ] Total Customers card shows **7,043**
- [ ] Churn Rate card shows **26.5%**
- [ ] Churned Customers card shows **1,869**
- [ ] Risk tier counts sum to **7,043**
- [ ] Page 2 default filter shows only active (Churn = No) customers
- [ ] `split` slicer correctly separates train_oof and test predictions

---

## Known Limitations

1. **Theme is unvalidated** — it was hand-written and could not be tested in Desktop.
2. **No PBIX included** — Power BI Desktop is not available in the dev environment.
3. **Scores have mixed provenance** — training customers have out-of-fold probabilities;
   test customers have final-model probabilities. The `split` column documents this.
   Do not present scores from different procedures as directly comparable.
4. **No timestamps** — the dataset is a single snapshot; tenure and TotalCharges for
   churned customers reflect values at the time of leaving.
