-- =============================================================
-- Telecom Retention Intelligence  -  SQL Analysis
-- Engine: PostgreSQL 16
-- Dataset: IBM Telco Customer Churn (7,043 rows x 21 columns)
-- Source:  https://github.com/IBM/telco-customer-churn-on-icp4d
-- License: Apache-2.0
-- =============================================================

-- -------------------------------------------------------
-- 0.  Schema and data load
-- -------------------------------------------------------
DROP TABLE IF EXISTS telco_raw CASCADE;

CREATE TABLE telco_raw (
    customerID       VARCHAR(20) PRIMARY KEY,
    gender           VARCHAR(10),
    SeniorCitizen    INTEGER,
    Partner          VARCHAR(5),
    Dependents       VARCHAR(5),
    tenure           INTEGER,
    PhoneService     VARCHAR(5),
    MultipleLines    VARCHAR(25),
    InternetService  VARCHAR(20),
    OnlineSecurity   VARCHAR(25),
    OnlineBackup     VARCHAR(25),
    DeviceProtection VARCHAR(25),
    TechSupport      VARCHAR(25),
    StreamingTV      VARCHAR(25),
    StreamingMovies  VARCHAR(25),
    Contract         VARCHAR(20),
    PaperlessBilling VARCHAR(5),
    PaymentMethod    VARCHAR(30),
    MonthlyCharges   NUMERIC(8,2),
    TotalCharges     VARCHAR(20),
    Churn            VARCHAR(5)
);

-- Load CSV (adjust the absolute path for your system):
-- \COPY telco_raw FROM '/absolute/path/to/data/Telco-Customer-Churn.csv'
--   WITH (FORMAT csv, HEADER true);

-- -------------------------------------------------------
-- 0b. Cleaning view: coerce blank TotalCharges to 0
-- -------------------------------------------------------
DROP VIEW IF EXISTS telco;

CREATE VIEW telco AS
SELECT
    customerID, gender, SeniorCitizen, Partner, Dependents,
    tenure, PhoneService, MultipleLines, InternetService,
    OnlineSecurity, OnlineBackup, DeviceProtection, TechSupport,
    StreamingTV, StreamingMovies, Contract, PaperlessBilling,
    PaymentMethod, MonthlyCharges,
    CASE
        WHEN TRIM(TotalCharges) = '' OR TotalCharges IS NULL THEN 0
        ELSE CAST(TotalCharges AS NUMERIC(10,2))
    END AS TotalCharges,
    Churn
FROM telco_raw;

-- =============================================================
-- QUERIES
-- =============================================================

-- -------------------------------------------------------
-- Q1: Overall churn
-- -------------------------------------------------------
SELECT
    COUNT(*)                                          AS total_customers,
    SUM(CASE WHEN Churn = 'Yes' THEN 1 ELSE 0 END)   AS churned,
    ROUND(100.0 * SUM(CASE WHEN Churn = 'Yes' THEN 1 ELSE 0 END)
          / COUNT(*), 2)                              AS churn_rate_pct,
    ROUND(AVG(tenure), 2)                             AS avg_tenure
FROM telco;

-- -------------------------------------------------------
-- Q2: Churn by contract type
-- -------------------------------------------------------
SELECT
    Contract,
    COUNT(*)                                          AS customers,
    SUM(CASE WHEN Churn = 'Yes' THEN 1 ELSE 0 END)   AS churned,
    ROUND(100.0 * SUM(CASE WHEN Churn = 'Yes' THEN 1 ELSE 0 END)
          / COUNT(*), 2)                              AS churn_rate_pct,
    ROUND(100.0 * SUM(CASE WHEN Churn = 'Yes' THEN 1 ELSE 0 END)
          / (SELECT SUM(CASE WHEN Churn = 'Yes' THEN 1 ELSE 0 END)
             FROM telco), 2)                          AS pct_of_all_churners
FROM telco
GROUP BY Contract
ORDER BY churn_rate_pct DESC;

-- -------------------------------------------------------
-- Q3: Churn by tenure band
-- -------------------------------------------------------
SELECT
    CASE
        WHEN tenure BETWEEN  0 AND 12 THEN '0-12 months'
        WHEN tenure BETWEEN 13 AND 24 THEN '13-24 months'
        WHEN tenure BETWEEN 25 AND 48 THEN '25-48 months'
        WHEN tenure BETWEEN 49 AND 72 THEN '49-72 months'
    END AS tenure_band,
    COUNT(*)                                          AS customers,
    SUM(CASE WHEN Churn = 'Yes' THEN 1 ELSE 0 END)   AS churned,
    ROUND(100.0 * SUM(CASE WHEN Churn = 'Yes' THEN 1 ELSE 0 END)
          / COUNT(*), 2)                              AS churn_rate_pct
FROM telco
GROUP BY tenure_band
ORDER BY tenure_band;

-- -------------------------------------------------------
-- Q4: Churn by payment method
-- -------------------------------------------------------
SELECT
    PaymentMethod,
    COUNT(*)                                          AS customers,
    SUM(CASE WHEN Churn = 'Yes' THEN 1 ELSE 0 END)   AS churned,
    ROUND(100.0 * SUM(CASE WHEN Churn = 'Yes' THEN 1 ELSE 0 END)
          / COUNT(*), 2)                              AS churn_rate_pct
FROM telco
GROUP BY PaymentMethod
ORDER BY churn_rate_pct DESC;

-- -------------------------------------------------------
-- Q5: Churn by internet service
-- -------------------------------------------------------
SELECT
    InternetService,
    COUNT(*)                                          AS customers,
    SUM(CASE WHEN Churn = 'Yes' THEN 1 ELSE 0 END)   AS churned,
    ROUND(100.0 * SUM(CASE WHEN Churn = 'Yes' THEN 1 ELSE 0 END)
          / COUNT(*), 2)                              AS churn_rate_pct
FROM telco
GROUP BY InternetService
ORDER BY churn_rate_pct DESC;

-- -------------------------------------------------------
-- Q6: Churn by tech support
-- -------------------------------------------------------
SELECT
    TechSupport,
    COUNT(*)                                          AS customers,
    SUM(CASE WHEN Churn = 'Yes' THEN 1 ELSE 0 END)   AS churned,
    ROUND(100.0 * SUM(CASE WHEN Churn = 'Yes' THEN 1 ELSE 0 END)
          / COUNT(*), 2)                              AS churn_rate_pct
FROM telco
GROUP BY TechSupport
ORDER BY churn_rate_pct DESC;

-- -------------------------------------------------------
-- Q7: Monthly charges and churn
-- -------------------------------------------------------
-- Q7a: Average charge by churn status
SELECT
    Churn,
    ROUND(AVG(MonthlyCharges), 2) AS avg_monthly_charges
FROM telco
GROUP BY Churn;

-- Q7b: Churn rate by charge quartile
SELECT
    quartile,
    MIN(MonthlyCharges)                               AS min_charge,
    MAX(MonthlyCharges)                               AS max_charge,
    COUNT(*)                                          AS customers,
    SUM(CASE WHEN Churn = 'Yes' THEN 1 ELSE 0 END)   AS churned,
    ROUND(100.0 * SUM(CASE WHEN Churn = 'Yes' THEN 1 ELSE 0 END)
          / COUNT(*), 2)                              AS churn_rate_pct
FROM (
    SELECT *, NTILE(4) OVER (ORDER BY MonthlyCharges) AS quartile
    FROM telco
) q
GROUP BY quartile
ORDER BY quartile;

-- -------------------------------------------------------
-- Q8: Revenue at risk
-- -------------------------------------------------------
SELECT
    ROUND(SUM(CASE WHEN Churn = 'Yes' THEN MonthlyCharges ELSE 0 END), 2)
                                                      AS churned_mrr,
    ROUND(SUM(MonthlyCharges), 2)                     AS total_mrr,
    ROUND(100.0 * SUM(CASE WHEN Churn = 'Yes' THEN MonthlyCharges ELSE 0 END)
          / SUM(MonthlyCharges), 2)                   AS pct_mrr_at_risk
FROM telco;

-- -------------------------------------------------------
-- Q9: Segmentation (contract x tenure band)
-- -------------------------------------------------------
SELECT
    Contract,
    CASE
        WHEN tenure BETWEEN  0 AND 12 THEN '0-12 months'
        WHEN tenure BETWEEN 13 AND 24 THEN '13-24 months'
        WHEN tenure BETWEEN 25 AND 48 THEN '25-48 months'
        WHEN tenure BETWEEN 49 AND 72 THEN '49-72 months'
    END AS tenure_band,
    COUNT(*)                                          AS customers,
    SUM(CASE WHEN Churn = 'Yes' THEN 1 ELSE 0 END)   AS churned,
    ROUND(100.0 * SUM(CASE WHEN Churn = 'Yes' THEN 1 ELSE 0 END)
          / COUNT(*), 2)                              AS churn_rate_pct
FROM telco
GROUP BY Contract, tenure_band
ORDER BY churn_rate_pct DESC;

-- -------------------------------------------------------
-- Q10: High-churn segments (contract x internet x payment)
--      At least 100 customers each, ranked by churn rate with lift
-- -------------------------------------------------------
SELECT
    Contract,
    InternetService,
    PaymentMethod,
    COUNT(*)                                          AS customers,
    SUM(CASE WHEN Churn = 'Yes' THEN 1 ELSE 0 END)   AS churned,
    ROUND(100.0 * SUM(CASE WHEN Churn = 'Yes' THEN 1 ELSE 0 END)
          / COUNT(*), 2)                              AS churn_rate_pct,
    ROUND((100.0 * SUM(CASE WHEN Churn = 'Yes' THEN 1 ELSE 0 END)
          / COUNT(*))
          / (SELECT 100.0 * SUM(CASE WHEN Churn = 'Yes' THEN 1 ELSE 0 END)
                   / COUNT(*) FROM telco), 2)         AS lift
FROM telco
GROUP BY Contract, InternetService, PaymentMethod
HAVING COUNT(*) >= 100
ORDER BY churn_rate_pct DESC;

-- -------------------------------------------------------
-- Q11: Protective add-ons vs churn (internet customers)
--      Excludes 1,526 customers with no internet service (churn 7.4%)
--      who have 0 add-ons by definition
-- -------------------------------------------------------
SELECT
    addon_count,
    COUNT(*)                                          AS customers,
    SUM(CASE WHEN Churn = 'Yes' THEN 1 ELSE 0 END)   AS churned,
    ROUND(100.0 * SUM(CASE WHEN Churn = 'Yes' THEN 1 ELSE 0 END)
          / COUNT(*), 2)                              AS churn_rate_pct
FROM (
    SELECT *,
        (CASE WHEN OnlineSecurity   = 'Yes' THEN 1 ELSE 0 END) +
        (CASE WHEN OnlineBackup     = 'Yes' THEN 1 ELSE 0 END) +
        (CASE WHEN DeviceProtection = 'Yes' THEN 1 ELSE 0 END) +
        (CASE WHEN TechSupport      = 'Yes' THEN 1 ELSE 0 END)
        AS addon_count
    FROM telco
    WHERE InternetService <> 'No'
) t
GROUP BY addon_count
ORDER BY addon_count;

-- -------------------------------------------------------
-- Q12: Demographics vs churn
-- -------------------------------------------------------
-- Q12a: Senior citizen
SELECT
    CASE WHEN SeniorCitizen = 1 THEN 'Senior' ELSE 'Non-Senior' END AS segment,
    COUNT(*)                                          AS customers,
    SUM(CASE WHEN Churn = 'Yes' THEN 1 ELSE 0 END)   AS churned,
    ROUND(100.0 * SUM(CASE WHEN Churn = 'Yes' THEN 1 ELSE 0 END)
          / COUNT(*), 2)                              AS churn_rate_pct
FROM telco
GROUP BY SeniorCitizen
ORDER BY churn_rate_pct DESC;

-- Q12b: Partner
SELECT
    Partner,
    COUNT(*)                                          AS customers,
    SUM(CASE WHEN Churn = 'Yes' THEN 1 ELSE 0 END)   AS churned,
    ROUND(100.0 * SUM(CASE WHEN Churn = 'Yes' THEN 1 ELSE 0 END)
          / COUNT(*), 2)                              AS churn_rate_pct
FROM telco
GROUP BY Partner
ORDER BY churn_rate_pct DESC;

-- Q12c: Dependents
SELECT
    Dependents,
    COUNT(*)                                          AS customers,
    SUM(CASE WHEN Churn = 'Yes' THEN 1 ELSE 0 END)   AS churned,
    ROUND(100.0 * SUM(CASE WHEN Churn = 'Yes' THEN 1 ELSE 0 END)
          / COUNT(*), 2)                              AS churn_rate_pct
FROM telco
GROUP BY Dependents
ORDER BY churn_rate_pct DESC;

-- -------------------------------------------------------
-- Q13: Retention opportunity
--      Top segments by churned MRR and size
-- -------------------------------------------------------
WITH segment_stats AS (
    SELECT
        Contract,
        InternetService,
        PaymentMethod,
        COUNT(*)                                          AS customers,
        SUM(CASE WHEN Churn = 'Yes' THEN 1 ELSE 0 END)   AS churned,
        ROUND(100.0 * SUM(CASE WHEN Churn = 'Yes' THEN 1 ELSE 0 END)
              / COUNT(*), 2)                              AS churn_rate_pct,
        ROUND(SUM(CASE WHEN Churn = 'Yes' THEN MonthlyCharges ELSE 0 END), 2)
                                                          AS churned_mrr,
        ROUND(AVG(MonthlyCharges), 2)                     AS avg_monthly_charge
    FROM telco
    GROUP BY Contract, InternetService, PaymentMethod
    HAVING COUNT(*) >= 50
)
SELECT *
FROM segment_stats
ORDER BY churned_mrr DESC, customers DESC
LIMIT 10;
