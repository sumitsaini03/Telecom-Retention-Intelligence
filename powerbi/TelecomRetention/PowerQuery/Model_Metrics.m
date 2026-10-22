let
    Source = Csv.Document(File.Contents(ProjectRoot & "/powerbi/data/ModelMetrics.csv"), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
    PromotedHeaders = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    TypedColumns = Table.TransformColumnTypes(PromotedHeaders, {{"model", type text},
        {"threshold", type number},
        {"threshold_source", type text},
        {"roc_auc", type number},
        {"pr_auc_average_precision", type number},
        {"precision", type number},
        {"recall", type number},
        {"f1", type number},
        {"accuracy", type number},
        {"specificity", type number},
        {"brier_score", type number},
        {"evaluation_size", Int64.Type},
        {"positive_count", Int64.Type},
        {"positive_prevalence", type number}}, "en-US")
in
    TypedColumns
