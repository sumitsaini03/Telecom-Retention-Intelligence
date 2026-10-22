let
    Source = Csv.Document(File.Contents(ProjectRoot & "/powerbi/data/Recommendations.csv"), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
    PromotedHeaders = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    TypedColumns = Table.TransformColumnTypes(PromotedHeaders, {{"finding", type text},
        {"supporting_metric", type text},
        {"observed_segment", type text},
        {"business_implication", type text},
        {"proposed_action", type text},
        {"priority", type text},
        {"validation_required", type text},
        {"evidence_scope", type text}}, "en-US")
in
    TypedColumns
