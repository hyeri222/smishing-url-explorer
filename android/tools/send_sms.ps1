param([string]$from = "15550100", [string]$text)
# 에뮬레이터에 '받은 문자'를 넣는다(시연·테스트용). 에뮬레이터 콘솔(5554)에 기존 인증 토큰으로 로그인.
$token = (Get-Content "$env:USERPROFILE\.emulator_console_auth_token" -Raw).Trim()
$c = New-Object System.Net.Sockets.TcpClient("127.0.0.1", 5554)
$s = $c.GetStream()
$enc = New-Object System.Text.UTF8Encoding($false)
function Send([string]$cmd) {
    $b = $enc.GetBytes($cmd + "`r`n"); $s.Write($b, 0, $b.Length); $s.Flush(); Start-Sleep -Milliseconds 400
    $buf = New-Object byte[] 4096; $n = 0
    while ($s.DataAvailable) { $n = $s.Read($buf, 0, 4096); $enc.GetString($buf, 0, $n) }
}
Start-Sleep -Milliseconds 400
$buf0 = New-Object byte[] 4096; while ($s.DataAvailable) { [void]$s.Read($buf0, 0, 4096) }  # 첫 안내문 버리기
"auth -> " + ((Send "auth $token") -join '').Trim()
"sms  -> " + ((Send "sms send $from $text") -join '').Trim()
[void](Send "quit"); $c.Close()
