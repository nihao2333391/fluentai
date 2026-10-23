param(
  [string]$OutputPath = ""
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing
$root = Split-Path -Parent $PSScriptRoot
if (-not $OutputPath) {
  $OutputPath = Join-Path $root "build-resources\icon.png"
}
$output = [System.IO.Path]::GetFullPath($OutputPath)
$directory = Split-Path -Parent $output
New-Item -ItemType Directory -Force -Path $directory | Out-Null

$bitmap = New-Object System.Drawing.Bitmap 512, 512
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$graphics.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
$graphics.Clear([System.Drawing.Color]::Transparent)

$path = New-Object System.Drawing.Drawing2D.GraphicsPath
$radius = 92
$diameter = $radius * 2
$rect = New-Object System.Drawing.Rectangle 20, 20, 472, 472
$path.AddArc($rect.X, $rect.Y, $diameter, $diameter, 180, 90)
$path.AddArc($rect.Right - $diameter, $rect.Y, $diameter, $diameter, 270, 90)
$path.AddArc($rect.Right - $diameter, $rect.Bottom - $diameter, $diameter, $diameter, 0, 90)
$path.AddArc($rect.X, $rect.Bottom - $diameter, $diameter, $diameter, 90, 90)
$path.CloseFigure()

$gradient = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
  $rect,
  [System.Drawing.Color]::FromArgb(255, 11, 18, 32),
  [System.Drawing.Color]::FromArgb(255, 15, 91, 160),
  45
)
$graphics.FillPath($gradient, $path)

$accent = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(255, 48, 196, 255))
$graphics.FillRectangle($accent, 116, 378, 280, 18)

$font = New-Object System.Drawing.Font("Segoe UI", 176, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
$textBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::White)
$format = New-Object System.Drawing.StringFormat
$format.Alignment = [System.Drawing.StringAlignment]::Center
$format.LineAlignment = [System.Drawing.StringAlignment]::Center
$graphics.DrawString("FA", $font, $textBrush, (New-Object System.Drawing.RectangleF 30, 90, 452, 280), $format)

$smallFont = New-Object System.Drawing.Font("Segoe UI", 30, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
$smallBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(220, 215, 237, 255))
$graphics.DrawString("FLUENT AI", $smallFont, $smallBrush, (New-Object System.Drawing.RectangleF 30, 400, 452, 60), $format)

$bitmap.Save($output, [System.Drawing.Imaging.ImageFormat]::Png)
$smallBrush.Dispose()
$smallFont.Dispose()
$format.Dispose()
$textBrush.Dispose()
$font.Dispose()
$accent.Dispose()
$gradient.Dispose()
$path.Dispose()
$graphics.Dispose()
$bitmap.Dispose()

Write-Host "Generated application icon: $output"
