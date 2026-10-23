param(
  [string]$InstallerPath = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$package = Get-Content -Raw (Join-Path $root "package.json") | ConvertFrom-Json
$version = [string]$package.version
if (-not $InstallerPath) {
  $InstallerPath = Join-Path $root "release\FluentAI-$version-x64-Setup.exe"
}
$installer = [System.IO.Path]::GetFullPath($InstallerPath)
if (-not (Test-Path -LiteralPath $installer -PathType Leaf)) {
  throw "Installer was not found: $installer"
}

$signatureStatus = "Unknown"
$signerSubject = $null
try {
  $signature = Get-AuthenticodeSignature -LiteralPath $installer
  $signatureStatus = [string]$signature.Status
  if ($signature.SignerCertificate) {
    $signerSubject = $signature.SignerCertificate.Subject
  }
}
catch {
  try {
    $certificate = [System.Security.Cryptography.X509Certificates.X509Certificate]::CreateFromSignedFile(
      $installer
    )
    $signatureStatus = "Signed"
    $signerSubject = $certificate.Subject
  }
  catch {
    $signatureStatus = "NotSigned"
  }
}
$stream = [System.IO.File]::OpenRead($installer)
try {
  $sha256 = [System.Security.Cryptography.SHA256]::Create()
  try {
    $hashBytes = $sha256.ComputeHash($stream)
  }
  finally {
    $sha256.Dispose()
  }
}
finally {
  $stream.Dispose()
}
$hash = ([System.BitConverter]::ToString($hashBytes) -replace '-', '').ToLowerInvariant()
$size = (Get-Item -LiteralPath $installer).Length
$shaPath = [System.IO.Path]::ChangeExtension($installer, ".sha256")
$manifestPath = Join-Path (Split-Path -Parent $installer) "release-manifest.json"
$relativeName = Split-Path -Leaf $installer

$shaLine = "$hash  $relativeName"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($shaPath, "$shaLine`n", $utf8NoBom)

$manifest = [ordered]@{
  product = "Fluent AI"
  version = $version
  created_at_utc = [DateTime]::UtcNow.ToString("o")
  installer = $relativeName
  installer_bytes = $size
  sha256 = $hash
  authenticode_status = $signatureStatus
  signer_subject = $signerSubject
  blockmap = if (Test-Path -LiteralPath "$installer.blockmap") { (Split-Path -Leaf "$installer.blockmap") } else { $null }
}
$manifestJson = $manifest | ConvertTo-Json -Depth 5
[System.IO.File]::WriteAllText($manifestPath, $manifestJson, $utf8NoBom)

if ($env:FLUENT_AI_REQUIRE_SIGNING -eq "1" -and $signatureStatus -ne "Valid") {
  throw "Signing was required, but the installer signature status is $signatureStatus."
}

Write-Host "RELEASE_MANIFEST_PASSED"
Write-Host " - installer: $relativeName"
Write-Host " - sha256: $hash"
Write-Host " - signature: $signatureStatus"
