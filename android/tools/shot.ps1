param([string]$name)
# 에뮬레이터 화면을 android/screens/<name>.png 로 저장 (작게 줄여서)
$adb = "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe"
$dir = Join-Path $PSScriptRoot "..\screens"
New-Item -ItemType Directory -Force $dir | Out-Null
& $adb shell screencap -p /sdcard/s.png
& $adb pull /sdcard/s.png "$dir\$name.png" | Out-Null
Add-Type -AssemblyName System.Drawing
$img = [System.Drawing.Image]::FromFile((Resolve-Path "$dir\$name.png"))
$w = 400; $h = [int]($img.Height * $w / $img.Width)
$bmp = New-Object System.Drawing.Bitmap $w, $h
$g = [System.Drawing.Graphics]::FromImage($bmp); $g.InterpolationMode = 'HighQualityBicubic'; $g.DrawImage($img, 0, 0, $w, $h)
$img.Dispose(); $g.Dispose()
$bmp.Save((Join-Path (Resolve-Path $dir) "$name.small.png"), [System.Drawing.Imaging.ImageFormat]::Png); $bmp.Dispose()
