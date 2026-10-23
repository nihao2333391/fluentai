$ErrorActionPreference = "Stop"
$cscLink = if ($env:CSC_LINK) { $env:CSC_LINK } else { $env:WIN_CSC_LINK }
$requireSigning = $env:FLUENT_AI_REQUIRE_SIGNING -eq "1"

if (-not $cscLink) {
  if ($requireSigning) {
    throw "FLUENT_AI_REQUIRE_SIGNING=1 but CSC_LINK/WIN_CSC_LINK is not configured."
  }
  Write-Host "SIGNING_NOT_CONFIGURED"
  Write-Host "Set CSC_LINK and CSC_KEY_PASSWORD to enable Authenticode signing."
  return
}

if (Test-Path -LiteralPath $cscLink) {
  $resolved = (Resolve-Path -LiteralPath $cscLink).Path
  if (-not (Test-Path -LiteralPath $resolved -PathType Leaf)) {
    throw "Code-signing certificate is not a file: $resolved"
  }
}

Write-Host "SIGNING_CONFIGURED"
