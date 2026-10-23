$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $python)) {
  throw "Python environment not found: $python. Run the M1 setup steps in README.md."
}

Push-Location $root
try {
  & pnpm lint
  if ($LASTEXITCODE -ne 0) { throw 'Frontend lint failed.' }

  & pnpm format:check
  if ($LASTEXITCODE -ne 0) { throw 'Formatting check failed.' }

  & pnpm typecheck
  if ($LASTEXITCODE -ne 0) { throw 'TypeScript check failed.' }

  & pnpm test
  if ($LASTEXITCODE -ne 0) { throw 'Frontend tests failed.' }

  & pnpm build
  if ($LASTEXITCODE -ne 0) { throw 'Electron build failed.' }

  $rendererLeak = Get-ChildItem -LiteralPath (Join-Path $root 'out\renderer') -Recurse -File |
    Select-String -Pattern 'FLUENT_AI_SIDECAR_TOKEN|Authorization: Bearer'
  if ($rendererLeak) { throw 'Sidecar authentication material leaked into the renderer bundle.' }

  & $python -m ruff check backend
  if ($LASTEXITCODE -ne 0) { throw 'Python lint failed.' }

  & $python -m ruff format --check backend
  if ($LASTEXITCODE -ne 0) { throw 'Python formatting check failed.' }

  & $python -m mypy --config-file backend\pyproject.toml backend\app backend\tests
  if ($LASTEXITCODE -ne 0) { throw 'Python type check failed.' }

  $env:PYTHONPATH = Join-Path $root 'backend'
  & $python -m pytest -q backend\tests
  if ($LASTEXITCODE -ne 0) { throw 'Python tests failed.' }

  & $python scripts\check_m0_reports.py
  if ($LASTEXITCODE -ne 0) { throw 'M0 regression check failed.' }

  & $python scripts\check_m6_report.py
  if ($LASTEXITCODE -ne 0) { throw 'M6 real-Fluent report check failed.' }

  & $python scripts\check_m7_workflow.py
  if ($LASTEXITCODE -ne 0) { throw 'M7 real workflow check failed.' }

  & $python scripts\check_meshing_schema.py
  if ($LASTEXITCODE -ne 0) { throw 'M8 Meshing schema check failed.' }

  & $python scripts\check_meshing_apply.py
  if ($LASTEXITCODE -ne 0) { throw 'M8 Meshing apply check failed.' }

  & $python scripts\check_meshing_interface.py
  if ($LASTEXITCODE -ne 0) { throw 'Meshing connection/read/write interface check failed.' }

  Write-Host 'M8_SCHEMA_CHECK_PASSED'
  Write-Host 'M8_APPLY_CHECK_PASSED'
  Write-Host 'MESHING_INTERFACE_CHECK_PASSED'
}
finally {
  Pop-Location
}
