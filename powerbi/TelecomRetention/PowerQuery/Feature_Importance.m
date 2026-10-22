let
    Source = Csv.Document(File.Contents(ProjectRoot & "/powerbi/data/FeatureImportanceTop10.csv"), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
    PromotedHeaders = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    TypedColumns = Table.TransformColumnTypes(PromotedHeaders, {{"rank", Int64.Type},
        {"feature", type text},
        {"mean_abs_shap", type number}}, "en-US")
in
    TypedColumns
