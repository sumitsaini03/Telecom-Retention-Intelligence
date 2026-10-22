let
    Source = Csv.Document(File.Contents(ProjectRoot & "/powerbi/data/ConfusionMatrix.csv"), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
    PromotedHeaders = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    TypedColumns = Table.TransformColumnTypes(PromotedHeaders, {{"model", type text},
        {"actual_outcome", type text},
        {"predicted_outcome", type text},
        {"customers", Int64.Type}}, "en-US")
in
    TypedColumns
