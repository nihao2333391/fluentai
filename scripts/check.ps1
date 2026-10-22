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

  Write-Host 'M4_CHECK_PASSED'
}
finally {
  Pop-Location
}