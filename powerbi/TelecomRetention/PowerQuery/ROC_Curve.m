let
    Source = Csv.Document(File.Contents(ProjectRoot & "/powerbi/data/ROCCurvePlot.csv"), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
    PromotedHeaders = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    TypedColumns = Table.TransformColumnTypes(PromotedHeaders, {{"model", type text},
        {"step", Int64.Type},
        {"x_value", type number},
        {"y_value", type number}}, "en-US")
in
    TypedColumns
