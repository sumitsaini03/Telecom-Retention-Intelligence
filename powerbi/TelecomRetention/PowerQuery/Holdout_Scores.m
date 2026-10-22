let
    Source = Csv.Document(File.Contents(ProjectRoot & "/powerbi/data/HoldoutScores.csv"), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
    PromotedHeaders = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    TypedColumns = Table.TransformColumnTypes(PromotedHeaders, {{"customerID", type text},
        {"Churn", type text},
        {"Churn_Flag", Int64.Type},
        {"tenure", Int64.Type},
        {"tenure_band", type text},
        {"tenure_band_order", Int64.Type},
        {"Contract", type text},
        {"InternetService", type text},
        {"PaymentMethod", type text},
        {"TechSupport", type text},
        {"MonthlyCharges", type number},
        {"MonthlyChargeBand", type text},
        {"ServiceCombination", type text},
        {"churn_probability", type number},
        {"predicted_churn", Int64.Type},
        {"risk_tier", type text},
        {"risk_tier_order", Int64.Type},
        {"model_identifier", type text},
        {"data_split", type text}}, "en-US")
in
    TypedColumns
