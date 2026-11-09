param([string]$text)
# 화면에서 글자가 $text를 포함하는 요소의 가운데를 누른다(시험용)
$adb = "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe"
& $adb shell uiautomator dump /sdcard/ui.xml | Out-Null
$tmp = Join-Path $env:TEMP "ui_dump.xml"
& $adb pull /sdcard/ui.xml $tmp | Out-Null
[xml]$doc = [IO.File]::ReadAllText($tmp, [Text.Encoding]::UTF8)
$node = $doc.SelectNodes("//node") | Where-Object { $_.text -like "*$text*" } | Select-Object -First 1
if (-not $node) { "없음: $text"; exit 1 }
$m = [regex]::Match($node.bounds, '\[(\d+),(\d+)\]\[(\d+),(\d+)\]')
$x = ([int]$m.Groups[1].Value + [int]$m.Groups[3].Value) / 2
$y = ([int]$m.Groups[2].Value + [int]$m.Groups[4].Value) / 2
& $adb shell input tap $x $y
"눌렀음: $($node.text) ($x,$y)"
