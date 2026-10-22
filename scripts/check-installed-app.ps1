param(
  [string]$InstallerPath = "",
  [string]$InstallDirectory = "",
  [switch]$KeepInstalled
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
if (-not $InstallerPath) {
  $InstallerPath = Join-Path $root "release\FluentAI-0.1.0-x64-Setup.exe"
}
if (-not $InstallDirectory) {
  $InstallDirectory = Join-Path $root "build\installed-smoke"
}
$installer = [System.IO.Path]::GetFullPath($InstallerPath)
$installDir = [System.IO.Path]::GetFullPath($InstallDirectory)
$allowedRoot = [System.IO.Path]::GetFullPath((Join-Path $root "build")) + [System.IO.Path]::DirectorySeparatorChar
if (-not $installDir.StartsWith($allowedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
  throw "Install directory must stay under the project build directory: $installDir"
}
if (-not (Test-Path -LiteralPath $installer)) {
  throw "Installer was not found: $installer"
}
$reportPath = Join-Path $root "docs\poc\reports\installer-smoke.json"
$smokeReportPath = Join-Path $root "build\installed-app-smoke.json"
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $reportPath) | Out-Null
Remove-Item -LiteralPath $smokeReportPath -Force -ErrorAction SilentlyContinue

$summary = [ordered]@{
  status = "failed"
  installer = $installer
  installer_bytes = (Get-Item -LiteralPath $installer).Length
  install_directory = $installDir
  started_at_utc = [DateTime]::UtcNow.ToString("o")
}
$appProcess = $null
try {
  if (Test-Path -LiteralPath $installDir) {
    Remove-Item -LiteralPath $installDir -Recurse -Force
  }

  $installerArguments = "/S /D=$installDir"
  $installProcess = Start-Process -FilePath $installer -ArgumentList $installerArguments `
    -PassThru -Wait -WindowStyle Hidden
  $summary["installer_exit_code"] = $installProcess.ExitCode
  if ($installProcess.ExitCode -ne 0) {
    throw "Installer exited with code $($installProcess.ExitCode)."
  }

  $appPath = Join-Path $installDir "FluentAI.exe"
  $sidecarRoot = Join-Path $installDir "resources\sidecar"
  foreach ($required in @($appPath, (Join-Path $sidecarRoot "python\python.exe"), (Join-Path $sidecarRoot "backend\app\sidecar.py"))) {
    if (-not (Test-Path -LiteralPath $required)) {
      throw "Installed file is missing: $required"
    }
  }
  $summary["app_path"] = $appPath
  $summary["sidecar_root"] = $sidecarRoot

  $oldSmokeTest = [Environment]::GetEnvironmentVariable("FLUENT_AI_SMOKE_TEST", "Process")
  $oldSmokeReport = [Environment]::GetEnvironmentVariable("FLUENT_AI_SMOKE_REPORT", "Process")
  $env:FLUENT_AI_SMOKE_TEST = "1"
  $env:FLUENT_AI_SMOKE_REPORT = $smokeReportPath
  try {
    $appProcess = Start-Process -FilePath $appPath -PassThru -WindowStyle Hidden
    if (-not $appProcess.WaitForExit(120000)) {
      throw "Installed application smoke test did not exit within 120 seconds."
    }
  } finally {
    [Environment]::SetEnvironmentVariable("FLUENT_AI_SMOKE_TEST", $oldSmokeTest, "Process")
    [Environment]::SetEnvironmentVariable("FLUENT_AI_SMOKE_REPORT", $oldSmokeReport, "Process")
  }

  if (-not (Test-Path -LiteralPath $smokeReportPath)) {
    throw "Installed application did not write a smoke report."
  }
  $smokeReport = Get-Content -Raw -LiteralPath $smokeReportPath | ConvertFrom-Json
  $summary["app_smoke"] = $smokeReport
  if ($smokeReport.status -ne "passed") {
    throw "Installed application smoke test failed: $($smokeReport.error)"
  }
  if (-not $smokeReport.is_packaged -or $smokeReport.sidecar.state -ne "ready") {
    throw "Installed application did not reach packaged sidecar readiness."
  }

  $summary["status"] = "passed"
  $summary["marker"] = "INSTALLER_SMOKE_PASSED"
  Write-Host "INSTALLER_SMOKE_PASSED"
} catch {
  $summary["error"] = $_.Exception.Message
  throw
} finally {
  if ($appProcess -and -not $appProcess.HasExited) {
    Stop-Process -Id $appProcess.Id -Force
  }
  if (-not $KeepInstalled) {
    $uninstaller = Join-Path $installDir "Uninstall Fluent AI.exe"
    if (Test-Path -LiteralPath $uninstaller) {
      try {
        Start-Process -FilePath $uninstaller -ArgumentList "/S" -Wait -WindowStyle Hidden | Out-Null
      } catch {
        $summary["uninstall_error"] = $_.Exception.Message
      }
    }
    if (Test-Path -LiteralPath $installDir) {
      Remove-Item -LiteralPath $installDir -Recurse -Force
    }
  }
  $summary["finished_at_utc"] = [DateTime]::UtcNow.ToString("o")
  $json = $summary | ConvertTo-Json -Depth 8
  $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllText($reportPath, $json, $utf8NoBom)
}
