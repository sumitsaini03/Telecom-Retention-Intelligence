-- Each named block is executed by scripts/run_postgres.py. All rates are
-- observed historical proportions, not causal effects or model predictions.

-- query: overall_churn
-- Business question: how many customers and churn events are in the source snapshot?
-- Churn-rate denominator: all customer rows.
SELECT COUNT(*) AS total_customers,
       COUNT(*) FILTER (WHERE churn = 'Yes') AS churned_customers,
       AVG((churn = 'Yes')::INT)::NUMERIC AS churn_rate,
       AVG(tenure)::NUMERIC(10, 2) AS average_tenure_months,
       AVG(monthly_charges)::NUMERIC(10, 2) AS average_monthly_charges
FROM telco_customers;

-- query: churn_by_contract
-- Churn-rate denominator: customers in the given contract group.
-- pct_of_all_churners denominator: all customers marked churned.
SELECT contract AS segment_value, COUNT(*) AS customers,
       COUNT(*) FILTER (WHERE churn = 'Yes') AS churned,
       AVG((churn = 'Yes')::INT)::NUMERIC AS churn_rate,
       COUNT(*) FILTER (WHERE churn = 'Yes')::NUMERIC
         / NULLIF((SELECT COUNT(*) FROM telco_customers WHERE churn = 'Yes'), 0) AS pct_of_all_churners
FROM telco_customers
GROUP BY contract
ORDER BY churn_rate DESC;

-- query: churn_by_tenure
-- Churn-rate denominator: customers in each tenure band; band boundaries are inclusive.
WITH banded AS (
    SELECT CASE WHEN tenure <= 12 THEN '0-12 months'
                WHEN tenure <= 24 THEN '13-24 months'
                WHEN tenure <= 48 THEN '25-48 months'
                ELSE '49-72 months' END AS segment_value,
           churn
    FROM telco_customers
)
SELECT segment_value, COUNT(*) AS customers,
       COUNT(*) FILTER (WHERE churn = 'Yes') AS churned,
       AVG((churn = 'Yes')::INT)::NUMERIC AS churn_rate
FROM banded
GROUP BY segment_value
ORDER BY CASE segment_value WHEN '0-12 months' THEN 1 WHEN '13-24 months' THEN 2
                            WHEN '25-48 months' THEN 3 ELSE 4 END;

-- query: churn_by_internet_service
-- Churn-rate denominator: customers in each internet-service group.
SELECT internet_service AS segment_value, COUNT(*) AS customers,
       COUNT(*) FILTER (WHERE churn = 'Yes') AS churned,
       AVG((churn = 'Yes')::INT)::NUMERIC AS churn_rate
FROM telco_customers
GROUP BY internet_service
ORDER BY churn_rate DESC;

-- query: churn_by_payment_method
-- Churn-rate denominator: customers in each payment-method group.
SELECT payment_method AS segment_value, COUNT(*) AS customers,
       COUNT(*) FILTER (WHERE churn = 'Yes') AS churned,
       AVG((churn = 'Yes')::INT)::NUMERIC AS churn_rate
FROM telco_customers
GROUP BY payment_method
ORDER BY churn_rate DESC;

-- query: average_charges_by_churn
-- Mean monthly-charge denominator: customers in each observed churn group.
SELECT churn AS segment_value, COUNT(*) AS customers,
       AVG(monthly_charges)::NUMERIC(10, 2) AS average_monthly_charges
FROM telco_customers
GROUP BY churn;

-- query: churn_by_senior_citizen
-- Churn-rate denominator: customers in each senior-citizen group.
SELECT CASE WHEN senior_citizen = 1 THEN 'Senior' ELSE 'Non-senior' END AS segment_value,
       COUNT(*) AS customers, COUNT(*) FILTER (WHERE churn = 'Yes') AS churned,
       AVG((churn = 'Yes')::INT)::NUMERIC AS churn_rate
FROM telco_customers
GROUP BY senior_citizen
ORDER BY senior_citizen;

-- query: churn_by_paperless_billing
-- Churn-rate denominator: customers in each paperless-billing group.
SELECT paperless_billing AS segment_value, COUNT(*) AS customers,
       COUNT(*) FILTER (WHERE churn = 'Yes') AS churned,
       AVG((churn = 'Yes')::INT)::NUMERIC AS churn_rate
FROM telco_customers
GROUP BY paperless_billing
ORDER BY churn_rate DESC;

-- query: churn_by_tech_support
-- Churn-rate denominator: customers in each support-service value, including no-internet service.
SELECT tech_support AS segment_value, COUNT(*) AS customers,
       COUNT(*) FILTER (WHERE churn = 'Yes') AS churned,
       AVG((churn = 'Yes')::INT)::NUMERIC AS churn_rate
FROM telco_customers
GROUP BY tech_support
ORDER BY churn_rate DESC;

-- query: addon_adoption_internet_only
-- Adoption denominator: customers with InternetService other than 'No'.
-- Customers without internet are deliberately excluded from both numerator and denominator.
SELECT addon.service AS segment_value,
       COUNT(*) AS internet_customers,
       COUNT(*) FILTER (WHERE addon.adopted) AS adopters,
       COUNT(*) FILTER (WHERE addon.adopted)::NUMERIC / NULLIF(COUNT(*), 0) AS adoption_rate
FROM telco_customers c
CROSS JOIN LATERAL (VALUES
    ('OnlineSecurity', c.online_security = 'Yes'),
    ('OnlineBackup', c.online_backup = 'Yes'),
    ('DeviceProtection', c.device_protection = 'Yes'),
    ('TechSupport', c.tech_support = 'Yes'),
    ('StreamingTV', c.streaming_tv = 'Yes'),
    ('StreamingMovies', c.streaming_movies = 'Yes')
) AS addon(service, adopted)
WHERE c.internet_service <> 'No'
GROUP BY addon.service
ORDER BY addon.service;

-- query: churn_by_addon_count
-- Population denominator: internet customers only; add-on count includes security,
-- backup, device protection, and technical support (each counted only when 'Yes').
WITH internet_customers AS (
    SELECT c.*,
           (CASE WHEN online_security = 'Yes' THEN 1 ELSE 0 END
          + CASE WHEN online_backup = 'Yes' THEN 1 ELSE 0 END
          + CASE WHEN device_protection = 'Yes' THEN 1 ELSE 0 END
          + CASE WHEN tech_support = 'Yes' THEN 1 ELSE 0 END) AS addon_count
    FROM telco_customers c
    WHERE internet_service <> 'No'
)
SELECT addon_count::TEXT AS segment_value, COUNT(*) AS customers,
       COUNT(*) FILTER (WHERE churn = 'Yes') AS churned,
       AVG((churn = 'Yes')::INT)::NUMERIC AS churn_rate
FROM internet_customers
GROUP BY addon_count
ORDER BY addon_count;

-- query: test_holdout_high_risk_active
-- Model population is held-out test predictions only. Active-customer denominator
-- includes only test-split rows with observed churn = 'No'.
SELECT s.risk_tier AS segment_value, COUNT(*) AS customers,
       AVG(s.churn_probability)::NUMERIC(10, 6) AS average_predicted_probability
FROM telco_model_scores s
WHERE s.data_split = 'test' AND s.observed_churn = 'No'
GROUP BY s.risk_tier
ORDER BY CASE s.risk_tier WHEN 'Critical' THEN 1 WHEN 'High' THEN 2
                          WHEN 'Medium' THEN 3 ELSE 4 END;

-- query: retention_priority_segments
-- The churn-rate denominator is all customers in each segment. Ranking uses
-- observed churned monthly charges as a prioritization descriptor, not profit.
SELECT contract, internet_service, payment_method,
       COUNT(*) AS customers,
       COUNT(*) FILTER (WHERE churn = 'Yes') AS churned,
       AVG((churn = 'Yes')::INT)::NUMERIC AS churn_rate,
       SUM(monthly_charges) FILTER (WHERE churn = 'Yes')::NUMERIC(12, 2) AS churned_monthly_charges,
       AVG(monthly_charges)::NUMERIC(10, 2) AS average_monthly_charges
FROM telco_customers
GROUP BY contract, internet_service, payment_method
HAVING COUNT(*) >= 50
ORDER BY churned_monthly_charges DESC, customers DESC
LIMIT 20;

-- query: churn_by_monthly_charge_quartile
-- Quartiles are based on all customer monthly charges; churn-rate denominator
-- is the number of customers assigned to the quartile.
WITH quartiles AS (
    SELECT *, NTILE(4) OVER (ORDER BY monthly_charges, customer_id) AS quartile
    FROM telco_customers
)
SELECT quartile::TEXT AS segment_value, COUNT(*) AS customers,
       COUNT(*) FILTER (WHERE churn = 'Yes') AS churned,
       AVG((churn = 'Yes')::INT)::NUMERIC AS churn_rate,
       MIN(monthly_charges)::NUMERIC(10, 2) AS minimum_monthly_charges,
       MAX(monthly_charges)::NUMERIC(10, 2) AS maximum_monthly_charges
FROM quartiles
GROUP BY quartile
ORDER BY quartile;
