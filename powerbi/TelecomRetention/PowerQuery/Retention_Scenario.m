let
    Source = Csv.Document(File.Contents(ProjectRoot & "/powerbi/data/RetentionScenario.csv"), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
    PromotedHeaders = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    TypedColumns = Table.TransformColumnTypes(PromotedHeaders, {{"segment", type text},
        {"segment_customers_observed", Int64.Type},
        {"historically_churned_observed", Int64.Type},
        {"historical_churn_rate_observed", type number},
        {"average_monthly_charges_observed", type number},
        {"effectiveness_assumption", type number},
        {"customers_retained_hypothetical", type number},
        {"gross_monthly_charges_retained_hypothetical", type number},
        {"gross_charges_over_assumed_months_hypothetical", type number},
        {"campaign_cost_hypothetical", type number},
        {"cost_per_contact_assumption", type number},
        {"retained_months_assumption", Int64.Type},
        {"interpretation", type text}}, "en-US")
in
    TypedColumns
