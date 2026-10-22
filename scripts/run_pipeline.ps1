$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot
python src/analysis.py
if ($LASTEXITCODE -ne 0) { throw "Analysis pipeline failed with exit code $LASTEXITCODE" }
