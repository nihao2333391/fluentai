param(
  [string]$OutputDirectory = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
if (-not $OutputDirectory) {
  $OutputDirectory = Join-Path $root "build\sidecar"
}
$output = [System.IO.Path]::GetFullPath($OutputDirectory)
$allowedRoot = [System.IO.Path]::GetFullPath((Join-Path $root "build")) + [System.IO.Path]::DirectorySeparatorChar
if (-not $output.StartsWith($allowedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
  throw "Sidecar output must stay under the project build directory: $output"
}

$venvPython = Join-Path $root ".venv\Scripts\python.exe"
$sitePackages = Join-Path $root ".venv\Lib\site-packages"
$pyvenvConfig = Join-Path $root ".venv\pyvenv.cfg"
if (-not (Test-Path -LiteralPath $venvPython)) {
  throw "Virtual-environment Python was not found: $venvPython"
}
if (-not (Test-Path -LiteralPath $sitePackages)) {
  throw "Virtual-environment site-packages was not found: $sitePackages"
}
if (-not (Test-Path -LiteralPath $pyvenvConfig)) {
  throw "pyvenv.cfg was not found: $pyvenvConfig"
}

$homeLine = Get-Content -LiteralPath $pyvenvConfig |
  Where-Object { $_ -match '^\s*home\s*=\s*(.+)$' } |
  Select-Object -First 1
if (-not $homeLine) {
  throw "The 'home' entry is missing from $pyvenvConfig"
}
$pythonHome = [regex]::Match($homeLine, '^\s*home\s*=\s*(.+)$').Groups[1].Value.Trim()
$pythonExecutable = Join-Path $pythonHome "python.exe"
if (-not (Test-Path -LiteralPath $pythonExecutable)) {
  throw "Base Python runtime was not found: $pythonExecutable"
}

if (Test-Path -LiteralPath $output) {
  Remove-Item -LiteralPath $output -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $output | Out-Null

$pythonDestination = Join-Path $output "python"
$siteDestination = Join-Path $output "site-packages"
$backendDestination = Join-Path $output "backend\app"
$schemaDestination = Join-Path $output "docs\meshing"

Write-Host "Copying Python runtime from $pythonHome"
New-Item -ItemType Directory -Force -Path $pythonDestination | Out-Null
Get-ChildItem -LiteralPath $pythonHome -Force |
  Copy-Item -Destination $pythonDestination -Recurse -Force
Write-Host "Copying sidecar dependencies"
New-Item -ItemType Directory -Force -Path $siteDestination | Out-Null
Get-ChildItem -LiteralPath $sitePackages -Force |
  Copy-Item -Destination $siteDestination -Recurse -Force
Write-Host "Copying backend application"
New-Item -ItemType Directory -Force -Path $backendDestination | Out-Null
Get-ChildItem -LiteralPath (Join-Path $root "backend\app") -Force |
  Copy-Item -Destination $backendDestination -Recurse -Force
New-Item -ItemType Directory -Force -Path $schemaDestination | Out-Null
Get-ChildItem -LiteralPath (Join-Path $root "docs\meshing") -Force |
  Copy-Item -Destination $schemaDestination -Recurse -Force

Get-ChildItem -LiteralPath $output -Recurse -Directory -Filter "__pycache__" | ForEach-Object {
  Remove-Item -LiteralPath $_.FullName -Recurse -Force
}
Get-ChildItem -LiteralPath $output -Recurse -File |
  Where-Object { $_.Extension -in ".pyc", ".pyo" } |
  ForEach-Object {
  Remove-Item -LiteralPath $_.FullName -Force
}

$runtimePrune = @(
  "python\Lib\test",
  "python\Lib\idlelib",
  "python\Lib\turtledemo",
  "python\Lib\ensurepip",
  "python\Lib\venv",
  "python\Lib\site-packages",
  "python\include",
  "python\libs",
  "python\Scripts",
  "python\tcl"
)
foreach ($relative in $runtimePrune) {
  $target = Join-Path $output $relative
  if (Test-Path -LiteralPath $target) {
    Remove-Item -LiteralPath $target -Recurse -Force
  }
}

$developmentPackages = @(
  "_pytest",
  "pytest",
  "mypy",
  "mypyc",
  "mypy_extensions",
  "ruff",
  "pandas_stubs",
  "types_pytz",
  "pip"
)
Get-ChildItem -LiteralPath $siteDestination -Force |
  Where-Object {
    $_.PSIsContainer -and (
      $developmentPackages -contains $_.Name -or
      $_.Name -match "^pytest[-_]" -or
      $_.Name -match "^types[-_]"
    )
  } |
  ForEach-Object {
    Remove-Item -LiteralPath $_.FullName -Recurse -Force
  }

$manifest = [ordered]@{
  name = "fluent-ai-sidecar"
  python_version = "3.12.14"
  python_source = $pythonHome
  prepared_at_utc = [DateTime]::UtcNow.ToString("o")
}
$manifestJson = $manifest | ConvertTo-Json
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText((Join-Path $output "manifest.json"), $manifestJson, $utf8NoBom)

$size = (Get-ChildItem -LiteralPath $output -Recurse -File | Measure-Object Length -Sum).Sum
Write-Host "Sidecar package prepared: $output"
Write-Host ("Sidecar size: {0:N1} MB" -f ($size / 1MB))
