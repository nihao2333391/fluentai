param(
  [string]$SidecarRoot = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
if (-not $SidecarRoot) {
  $SidecarRoot = Join-Path $root "build\sidecar"
}
$sidecarRoot = [System.IO.Path]::GetFullPath($SidecarRoot)
$python = Join-Path $sidecarRoot "python\python.exe"
$backend = Join-Path $sidecarRoot "backend"
$sitePackages = Join-Path $sidecarRoot "site-packages"
$dataDirectory = Join-Path $root "build\packaging-smoke-data"
$stdoutPath = Join-Path $root "build\packaging-sidecar.stdout.log"
$stderrPath = Join-Path $root "build\packaging-sidecar.stderr.log"
$reportPath = Join-Path $root "docs\poc\reports\packaging-sidecar.json"
$curl = (Get-Command curl.exe -ErrorAction Stop).Source

foreach ($required in @($python, $backend, $sitePackages)) {
  if (-not (Test-Path -LiteralPath $required)) {
    throw "Required packaged sidecar path is missing: $required"
  }
}
New-Item -ItemType Directory -Force -Path $dataDirectory | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $reportPath) | Out-Null
Remove-Item -LiteralPath $stdoutPath, $stderrPath -Force -ErrorAction SilentlyContinue

$tokenBytes = New-Object byte[] 32
$random = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$random.GetBytes($tokenBytes)
$random.Dispose()
$token = -join ($tokenBytes | ForEach-Object { $_.ToString("x2") })

$oldEnvironment = @{}
foreach ($name in @(
  "FLUENT_AI_SIDECAR_TOKEN",
  "FLUENT_AI_PARENT_PIPE",
  "FLUENT_AI_DATA_DIR",
  "PYTHONPATH",
  "PYTHONHOME",
  "PYTHONNOUSERSITE",
  "PYTHONUNBUFFERED"
)) {
  $oldEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
}
$env:FLUENT_AI_SIDECAR_TOKEN = $token
$env:FLUENT_AI_PARENT_PIPE = $null
$env:FLUENT_AI_DATA_DIR = $dataDirectory
$env:PYTHONPATH = "$backend;$sitePackages"
$env:PYTHONHOME = (Join-Path $sidecarRoot "python")
$env:PYTHONNOUSERSITE = "1"
$env:PYTHONUNBUFFERED = "1"

$summary = [ordered]@{
  status = "failed"
  started_at_utc = [DateTime]::UtcNow.ToString("o")
  python = $python
  sidecar_root = $sidecarRoot
}
$process = $null
try {
  $process = Start-Process -FilePath $python -ArgumentList @("-m", "app.sidecar") `
    -WorkingDirectory $backend -RedirectStandardOutput $stdoutPath `
    -RedirectStandardError $stderrPath -PassThru -WindowStyle Hidden
  $summary["pid"] = $process.Id

  $handshake = $null
  $deadline = [DateTime]::UtcNow.AddSeconds(90)
  while ([DateTime]::UtcNow -lt $deadline) {
    if (Test-Path -LiteralPath $stdoutPath) {
      $lines = Get-Content -LiteralPath $stdoutPath -ErrorAction SilentlyContinue
      foreach ($line in $lines) {
        if ($line -match '"event"\s*:\s*"sidecar_ready"') {
          $handshake = $line | ConvertFrom-Json
          break
        }
        if ($line -match '"event"\s*:\s*"sidecar_error"') {
          throw "Packaged sidecar reported an error: $line"
        }
      }
    }
    if ($handshake) { break }
    if ($process.HasExited) {
      $stderr = if (Test-Path -LiteralPath $stderrPath) {
        Get-Content -Raw -LiteralPath $stderrPath
      } else { "" }
      throw "Packaged sidecar exited before readiness. $stderr"
    }
    Start-Sleep -Milliseconds 500
  }
  if (-not $handshake) {
    throw "Timed out waiting for the packaged sidecar handshake."
  }
  $summary["handshake"] = $handshake

  $headers = "Authorization: Bearer $token"
  $readyUrl = "http://127.0.0.1:{0}/api/system/ready" -f $handshake.port
  $readyJson = & $curl --silent --show-error --fail --max-time 30 -H $headers $readyUrl
  if ($LASTEXITCODE -ne 0) {
    throw "Packaged sidecar readiness request failed with curl exit code $LASTEXITCODE."
  }
  $ready = $readyJson | ConvertFrom-Json
  $summary["ready"] = $ready
  if ($ready.status -ne "ready" -or $ready.database -ne "ready") {
    throw "Packaged sidecar readiness response was invalid."
  }

  $shutdownUrl = "http://127.0.0.1:{0}/api/system/shutdown" -f $handshake.port
  $shutdownJson = & $curl --silent --show-error --fail --max-time 30 -X POST -H $headers $shutdownUrl
  if ($LASTEXITCODE -ne 0) {
    throw "Packaged sidecar shutdown request failed with curl exit code $LASTEXITCODE."
  }
  $summary["shutdown"] = $shutdownJson | ConvertFrom-Json
  if (-not $process.WaitForExit(30000)) {
    throw "Packaged sidecar did not shut down within 30 seconds."
  }
  $exitCode = $process.ExitCode
  $summary["exit_code"] = $exitCode
  if ($null -ne $exitCode -and $exitCode -ne 0) {
    $stderr = if (Test-Path -LiteralPath $stderrPath) {
      Get-Content -Raw -LiteralPath $stderrPath
    } else { "" }
    throw "Packaged sidecar exited with code $exitCode`: $stderr"
  }
  if (Get-Process -Id $process.Id -ErrorAction SilentlyContinue) {
    throw "Packaged sidecar process is still running after shutdown."
  }
  $summary["status"] = "passed"
  $summary["marker"] = "PACKAGED_SIDECAR_CHECK_PASSED"
  Write-Host "PACKAGED_SIDECAR_CHECK_PASSED"
} catch {
  $summary["error"] = $_.Exception.Message
  if (Test-Path -LiteralPath $stderrPath) {
    $summary["stderr"] = Get-Content -Raw -LiteralPath $stderrPath
  }
  throw
} finally {
  if ($process -and -not $process.HasExited) {
    Stop-Process -Id $process.Id -Force
  }
  foreach ($name in $oldEnvironment.Keys) {
    [Environment]::SetEnvironmentVariable($name, $oldEnvironment[$name], "Process")
  }
  $summary["finished_at_utc"] = [DateTime]::UtcNow.ToString("o")
  $json = $summary | ConvertTo-Json -Depth 8
  $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllText($reportPath, $json, $utf8NoBom)
}
