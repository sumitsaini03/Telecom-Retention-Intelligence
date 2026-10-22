-- PostgreSQL 16+ schema for the IBM Telco Customer Churn source data.
-- Data is rebuilt transactionally by scripts/run_postgres.py.
CREATE TABLE IF NOT EXISTS telco_customers (
    customer_id TEXT PRIMARY KEY,
    gender TEXT NOT NULL CHECK (gender IN ('Female', 'Male')),
    senior_citizen SMALLINT NOT NULL CHECK (senior_citizen IN (0, 1)),
    partner TEXT NOT NULL CHECK (partner IN ('Yes', 'No')),
    dependents TEXT NOT NULL CHECK (dependents IN ('Yes', 'No')),
    tenure SMALLINT NOT NULL CHECK (tenure BETWEEN 0 AND 72),
    phone_service TEXT NOT NULL CHECK (phone_service IN ('Yes', 'No')),
    multiple_lines TEXT NOT NULL CHECK (multiple_lines IN ('Yes', 'No', 'No phone service')),
    internet_service TEXT NOT NULL CHECK (internet_service IN ('DSL', 'Fiber optic', 'No')),
    online_security TEXT NOT NULL CHECK (online_security IN ('Yes', 'No', 'No internet service')),
    online_backup TEXT NOT NULL CHECK (online_backup IN ('Yes', 'No', 'No internet service')),
    device_protection TEXT NOT NULL CHECK (device_protection IN ('Yes', 'No', 'No internet service')),
    tech_support TEXT NOT NULL CHECK (tech_support IN ('Yes', 'No', 'No internet service')),
    streaming_tv TEXT NOT NULL CHECK (streaming_tv IN ('Yes', 'No', 'No internet service')),
    streaming_movies TEXT NOT NULL CHECK (streaming_movies IN ('Yes', 'No', 'No internet service')),
    contract TEXT NOT NULL CHECK (contract IN ('Month-to-month', 'One year', 'Two year')),
    paperless_billing TEXT NOT NULL CHECK (paperless_billing IN ('Yes', 'No')),
    payment_method TEXT NOT NULL CHECK (payment_method IN (
        'Electronic check', 'Mailed check', 'Bank transfer (automatic)', 'Credit card (automatic)'
    )),
    monthly_charges NUMERIC(10, 2) NOT NULL CHECK (monthly_charges >= 0),
    total_charges NUMERIC(12, 2) NOT NULL CHECK (total_charges >= 0),
    churn TEXT NOT NULL CHECK (churn IN ('Yes', 'No'))
);

CREATE TABLE IF NOT EXISTS telco_model_scores (
    customer_id TEXT PRIMARY KEY REFERENCES telco_customers(customer_id),
    observed_churn TEXT NOT NULL CHECK (observed_churn IN ('Yes', 'No')),
    churn_probability DOUBLE PRECISION NOT NULL CHECK (churn_probability BETWEEN 0 AND 1),
    predicted_churn SMALLINT NOT NULL CHECK (predicted_churn IN (0, 1)),
    risk_tier TEXT NOT NULL CHECK (risk_tier IN ('Low', 'Medium', 'High', 'Critical')),
    model_identifier TEXT NOT NULL,
    data_split TEXT NOT NULL CHECK (data_split IN ('train_oof', 'test'))
);

CREATE INDEX IF NOT EXISTS idx_telco_customers_churn ON telco_customers(churn);
CREATE INDEX IF NOT EXISTS idx_telco_customers_contract ON telco_customers(contract);
CREATE INDEX IF NOT EXISTS idx_telco_model_scores_split_tier ON telco_model_scores(data_split, risk_tier);
