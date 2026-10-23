param(
  [ValidateSet("dir", "nsis")]
  [string]$Target = "nsis"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
  if (-not $env:ELECTRON_BUILDER_BINARIES_MIRROR) {
    $env:ELECTRON_BUILDER_BINARIES_MIRROR = "https://npmmirror.com/mirrors/electron-builder-binaries/"
  }

  & pnpm build
  if ($LASTEXITCODE -ne 0) { throw "Electron build failed." }

  & pnpm package:sidecar
  if ($LASTEXITCODE -ne 0) { throw "Sidecar staging failed." }

  & pnpm package:check-sidecar
  if ($LASTEXITCODE -ne 0) { throw "Packaged sidecar verification failed." }

  & powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/check-signing-config.ps1
  if ($LASTEXITCODE -ne 0) { throw "Code-signing preflight failed." }

  if ($Target -eq "dir") {
    & pnpm exec electron-builder --win --dir --config electron-builder.yml
    if ($LASTEXITCODE -ne 0) { throw "Unpacked Windows package failed." }
    Write-Host "PACKAGE_DIR_PASSED"
    return
  }

  & pnpm exec electron-builder --win nsis --config electron-builder.yml
  if ($LASTEXITCODE -ne 0) { throw "NSIS installer build failed." }

  & pnpm package:check-installed
  if ($LASTEXITCODE -ne 0) { throw "Installed application verification failed." }

  & powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/finalize-release.ps1
  if ($LASTEXITCODE -ne 0) { throw "Release manifest generation failed." }

  Write-Host "PACKAGE_WIN_PASSED"
} finally {
  Pop-Location
}
