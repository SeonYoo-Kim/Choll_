# 추종·이동 명령 로컬 스모크 테스트 (main 머지 전 develop 검증용)
#
# 사용법 (저장소 루트에서):
#   powershell -ExecutionPolicy Bypass -File tests\smoke\run_local_smoke.ps1
#   powershell -ExecutionPolicy Bypass -File tests\smoke\run_local_smoke.ps1 -FakeHeartbeat   # 실카트(RPi) 없이
#
# 하는 일:
#   1) 로컬 BE 기동(이미 8080 떠 있으면 재사용) + 헬스 체크
#   2) MQTT 관찰자(cmd/move/cart 구독) + WS 리스너 기동
#   3) 카트 ONLINE 대기 (실카트 하트비트 / -FakeHeartbeat면 가짜 발행)
#   4) FOLLOW·NAV REST 시나리오 자동 실행 → PASS/FAIL 요약
#   5) MQTT·WS 수신 로그 검증
# 끝나도 BE는 살려둔다 (FE 붙여서 수동 확인용). 종료 방법은 마지막에 출력.

param(
    [switch]$FakeHeartbeat
)

$ErrorActionPreference = 'Continue'
$root = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$logDir = Join-Path $env:TEMP 'choll-smoke'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$cmdLog = Join-Path $logDir "cmd_$stamp.txt"
$wsLog = Join-Path $logDir "ws_$stamp.txt"
$beLog = Join-Path $logDir "be_$stamp.txt"
New-Item -ItemType Directory -Force $logDir | Out-Null

$python = Join-Path $env:USERPROFILE 'miniforge3\python.exe'
if (-not (Test-Path $python)) { $python = 'python' }

$base = 'http://localhost:8080/api/carts/1'
$script:pass = 0
$script:fail = 0
$results = New-Object System.Collections.ArrayList

function Invoke-Api($method, $url, $body) {
    try {
        $p = @{Method = $method; Uri = $url; UseBasicParsing = $true; TimeoutSec = 10}
        if ($body) { $p.Body = $body; $p.ContentType = 'application/json' }
        $r = Invoke-WebRequest @p
        return @{Status = [int]$r.StatusCode; Body = [string]$r.Content}
    } catch {
        $resp = $_.Exception.Response
        if ($resp) {
            $sr = New-Object IO.StreamReader($resp.GetResponseStream())
            return @{Status = [int]$resp.StatusCode; Body = $sr.ReadToEnd()}
        }
        return @{Status = -1; Body = $_.Exception.Message}
    }
}

function Assert-Case($name, $method, $url, $body, $expectedStatus, $bodyPattern) {
    $r = Invoke-Api $method $url $body
    $ok = ($r.Status -eq $expectedStatus)
    if ($ok -and $bodyPattern) { $ok = ($r.Body -match $bodyPattern) }
    if ($ok) { $script:pass++; $mark = 'PASS' } else { $script:fail++; $mark = 'FAIL' }
    [void]$results.Add("[$mark] $name -> $($r.Status) $($r.Body)")
    Write-Host "[$mark] $name -> $($r.Status)"
}

function Assert-Log($name, $path, $pattern) {
    $content = ''
    if (Test-Path $path) { $content = Get-Content $path -Raw }
    if ($content -match $pattern) { $script:pass++; $mark = 'PASS' }
    else { $script:fail++; $mark = 'FAIL' }
    [void]$results.Add("[$mark] $name (로그: $pattern)")
    Write-Host "[$mark] $name"
}

Write-Host "=== 쫄래쫄래 로컬 스모크 테스트 ($stamp) ==="
Push-Location $root
Write-Host ("코드 기준: " + (git log -1 --format='%h %s') + " / 브랜치: " + (git rev-parse --abbrev-ref HEAD))

# 1) 사전 점검
if (-not (Test-Path (Join-Path $root 'backend\.env'))) {
    Write-Host 'FAIL: backend\.env 가 없습니다 (DB·MQTT 자격증명 필요)'; Pop-Location; exit 1
}
if (-not (Get-NetTCPConnection -LocalPort 3306 -State Listen -ErrorAction SilentlyContinue)) {
    Write-Host 'FAIL: 로컬 MySQL(3306)이 떠 있지 않습니다'; Pop-Location; exit 1
}

# 2) BE 기동 (이미 떠 있으면 재사용)
$bePid = $null
if (Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue) {
    Write-Host 'BE: 8080이 이미 떠 있어 재사용합니다'
} else {
    Write-Host "BE 기동 중... (로그: $beLog)"
    $proc = Start-Process -FilePath (Join-Path $root 'backend\gradlew.bat') `
        -ArgumentList '-p', (Join-Path $root 'backend'), 'bootRun', '--console=plain' `
        -WorkingDirectory $root -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $beLog -RedirectStandardError "$beLog.err"
    $bePid = $proc.Id
}
$healthy = $false
for ($i = 0; $i -lt 45; $i++) {
    $r = Invoke-Api GET $base $null
    if ($r.Status -eq 200) { $healthy = $true; break }
    Start-Sleep -Seconds 2
}
if (-not $healthy) { Write-Host "FAIL: BE 헬스 체크 실패 — $beLog 확인"; Pop-Location; exit 1 }
Write-Host 'BE: 헬스 체크 OK'

# 3) 관찰자 기동 (이전 실행이 남긴 관찰자가 있으면 먼저 정리 — 재실행 충돌 방지)
$pidFile = Join-Path $logDir 'observers.pid'
if (Test-Path $pidFile) {
    Get-Content $pidFile | ForEach-Object {
        try { Stop-Process -Id ([int]$_) -Force -Confirm:$false -ErrorAction Stop; Write-Host "이전 관찰자(PID $_) 정리" } catch {}
    }
    Remove-Item $pidFile -Force
}
$obsArgs = @((Join-Path $PSScriptRoot 'mqtt_cart.py'), '--log', $cmdLog, '--duration', '3600')
if ($FakeHeartbeat) { $obsArgs += '--heartbeat'; Write-Host '가짜 하트비트 모드 (실카트 없음)' }
$obs = Start-Process -FilePath $python -ArgumentList $obsArgs -WindowStyle Hidden -PassThru
$wsl = Start-Process -FilePath $python `
    -ArgumentList (Join-Path $PSScriptRoot 'ws_listener.py'), '--log', $wsLog `
    -WindowStyle Hidden -PassThru
@($obs.Id, $wsl.Id) | Out-File $pidFile -Encoding ascii
Start-Sleep -Seconds 3

# 4) 카트 ONLINE 대기 (실카트: RPi 하트비트 5초 주기)
Write-Host '카트 ONLINE 대기 중 (최대 60초)...'
$online = $false
for ($i = 0; $i -lt 30; $i++) {
    $r = Invoke-Api GET $base $null
    if ($r.Body -match '"online":true') { $online = $true; break }
    Start-Sleep -Seconds 2
}
if ($online) { $script:pass++; [void]$results.Add('[PASS] 카트 ONLINE (하트비트 수신)') ; Write-Host '[PASS] 카트 ONLINE' }
else {
    $script:fail++; [void]$results.Add('[FAIL] 카트 ONLINE 안 됨 — RPi 하트비트(status/cart) 확인 또는 -FakeHeartbeat 사용')
    Write-Host '[FAIL] 카트가 ONLINE이 아닙니다. RPi 전원·브로커 연결을 확인하세요. (이후 추종 케이스는 400이 나올 수 있음)'
}

# 5) REST 시나리오
Assert-Case '405 프로브 (새 엔드포인트 배포 확인)' GET  "$base/follow/pause" $null 405 $null
Assert-Case '추종 시작 202'                     POST "$base/follow"       $null 202 '"status":"FOLLOWING"'
Assert-Case '중복 시작 400'                     POST "$base/follow"       $null 400 '이미 추종 중'
Assert-Case '일시정지 202'                      POST "$base/follow/pause" $null 202 '"status":"PAUSED"'
Assert-Case '일시정지 멱등 202'                 POST "$base/follow/pause" $null 202 '"status":"PAUSED"'
Assert-Case '재개 202 (같은 followId)'          POST "$base/follow"       $null 202 '"status":"FOLLOWING"'
Assert-Case '종료 204'                          DELETE "$base/follow"     $null 204 $null
Assert-Case '종료 멱등 204'                     DELETE "$base/follow"     $null 204 $null
Assert-Case '무세션 일시정지 400'               POST "$base/follow/pause" $null 400 '진행 중인 추종이 없어'
Assert-Case '이동 시작 202'                     POST "$base/navigation"   '{"zoneId":1}' 202 '"status":"ACCEPTED"'
Assert-Case '이동 중 추종 시작 400'             POST "$base/follow"       $null 400 '이동 중'
Assert-Case '이동 취소 204'                     DELETE "$base/navigation" $null 204 $null
Assert-Case '픽셀 클릭 이동 202'                POST "$base/navigation"   '{"zoneId":1,"x":612.5,"y":431.0}' 202 '"status":"ACCEPTED"'
Assert-Case '이동 취소(정리) 204'               DELETE "$base/navigation" $null 204 $null

# 6) MQTT·WS 수신 검증 (전파 대기 후)
Start-Sleep -Seconds 3
Assert-Log 'MQTT: FOLLOW_START 수신'  $cmdLog 'FOLLOW_START'
Assert-Log 'MQTT: FOLLOW_PAUSE 수신'  $cmdLog 'FOLLOW_PAUSE'
Assert-Log 'MQTT: FOLLOW_STOP 수신'   $cmdLog 'FOLLOW_STOP'
Assert-Log 'MQTT: MOVE(픽셀 클릭) 수신' $cmdLog '"pixel":\{"x":612\.5'
Assert-Log 'MQTT: CANCEL 수신'        $cmdLog '"command":"CANCEL"'
Assert-Log 'WS: FOLLOWING 이벤트'     $wsLog  '"status":"FOLLOWING"'
Assert-Log 'WS: PAUSED 이벤트'        $wsLog  '"status":"PAUSED"'
Assert-Log 'WS: STOPPED 이벤트'       $wsLog  '"status":"STOPPED"'
Assert-Log 'WS: NAV ACCEPTED 이벤트'  $wsLog  '"status":"ACCEPTED"'

# 7) 요약
Write-Host ''
Write-Host "=== 결과: PASS $script:pass / FAIL $script:fail ==="
$summary = Join-Path $logDir "summary_$stamp.txt"
$results | Out-File $summary -Encoding utf8
Write-Host "상세: $summary"
Write-Host "명령 수신 로그: $cmdLog"
Write-Host "WS 수신 로그:   $wsLog"
Write-Host ''
Write-Host '수동 확인 남은 것:'
Write-Host ' - (실카트) RPi 전원 끄고 15초 뒤 POST /follow -> 400 "오프라인" 인지'
Write-Host ' - FE dev 서버 붙여서 추종 버튼 시작/일시정지/종료 동작'
Write-Host ' - 젯슨 fe_bridge 로그에 FOLLOW_* 무시 외 오류 없는지'
Write-Host ''
Write-Host 'BE는 계속 실행 중입니다 (FE 수동 확인용).'
if ($bePid) { Write-Host "끝나면 종료: Stop-Process -Id $bePid  (관찰자: $($obs.Id), $($wsl.Id))" }
else { Write-Host "관찰자 종료: Stop-Process -Id $($obs.Id), $($wsl.Id)" }
Pop-Location
if ($script:fail -gt 0) { exit 1 } else { exit 0 }
