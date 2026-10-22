param([switch]$Refresh)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$dataDir = Join-Path $repoRoot 'data'
$destination = Join-Path $dataDir 'Telco-Customer-Churn.csv'
$temporary = Join-Path $dataDir 'Telco-Customer-Churn.download.csv'
$metadataPath = Join-Path $dataDir 'source_metadata.json'
$sourceUrl = 'https://raw.githubusercontent.com/IBM/telco-customer-churn-on-icp4d/master/data/Telco-Customer-Churn.csv'

if ((Test-Path -LiteralPath $destination) -and -not $Refresh) {
    $existing = Get-Item -LiteralPath $destination
    $hash = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant()
    Write-Output "Preserved existing dataset: $($existing.Length) bytes; SHA-256 $hash"
    if (Test-Path -LiteralPath $metadataPath) {
        $metadata = Get-Content -Raw -LiteralPath $metadataPath | ConvertFrom-Json
        if ($metadata.sha256 -and $metadata.sha256.ToLowerInvariant() -ne $hash) {
            throw 'Existing dataset does not match data/source_metadata.json; use -Refresh only after reviewing the source.'
        }
    }
    exit 0
}

$response = Invoke-WebRequest -Uri $sourceUrl -TimeoutSec 60 -OutFile $temporary -PassThru
if ([int]$response.StatusCode -ne 200) { throw "Dataset request returned HTTP $($response.StatusCode)" }
$finalUrl = $response.BaseResponse.RequestMessage.RequestUri.AbsoluteUri
$download = Get-Item -LiteralPath $temporary
$sha256 = (Get-FileHash -LiteralPath $temporary -Algorithm SHA256).Hash.ToLowerInvariant()
Move-Item -LiteralPath $temporary -Destination $destination -Force
$metadata = [ordered]@{
    source_url = $sourceUrl
    final_url = $finalUrl
    retrieval_date = (Get-Date).ToString('yyyy-MM-dd')
    http_status = [int]$response.StatusCode
    bytes = $download.Length
    sha256 = $sha256
    verification = 'Downloaded from the stated IBM repository raw URL.'
}
$metadata | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $metadataPath -Encoding utf8
Write-Output "Downloaded $($download.Length) bytes; SHA-256 $sha256; final URL $finalUrl"
