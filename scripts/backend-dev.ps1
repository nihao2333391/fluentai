$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $python)) {
  throw "Python environment not found: $python. Run the setup steps in README.md."
}

Push-Location $root
try {
  & $python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8765 --reload
}
finally {
  Pop-Location
}