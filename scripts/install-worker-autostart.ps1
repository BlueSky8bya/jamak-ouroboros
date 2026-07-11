# install-worker-autostart.ps1
# 'jamak-worker' 를 Windows 작업 스케줄러에 등록 → 로그온할 때마다 백그라운드에서
# jamak worker 가 자동으로 뜬다. 그러면 웹앱에 유튜브 링크만 붙여넣으면 알아서
# 처리된다 (더 이상 파워셸에 명령을 칠 필요 없음).
#
# 딱 한 번만 실행하면 된다 (프로젝트 폴더에서):
#   powershell -ExecutionPolicy Bypass -File scripts\install-worker-autostart.ps1
#
# 나중에 자동시작을 끄려면:
#   Unregister-ScheduledTask -TaskName "jamak-worker" -Confirm:$false
#
# 필요조건: DATABASE_URL(클라우드 DB) 와 ANTHROPIC_API_KEY 가 이 사용자 계정의
# 환경변수(User)로 설정돼 있어야 한다. 로그온 작업은 그 값들을 그대로 물려받는다.

$ErrorActionPreference = "Stop"
$TaskName = "jamak-worker"
$wrapper  = Join-Path $PSScriptRoot "run-worker.ps1"

if (-not (Test-Path $wrapper)) {
  throw "run-worker.ps1 을 찾을 수 없습니다: $wrapper"
}

# worker 가 uv 로 파이프라인을 띄우므로 uv 가 있는지 먼저 확인
$uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
if (-not $uv) {
  foreach ($p in @("$env:USERPROFILE\.local\bin\uv.exe",
                   "$env:LOCALAPPDATA\Microsoft\WinGet\Links\uv.exe")) {
    if (Test-Path $p) { $uv = $p; break }
  }
}
if (-not $uv) {
  Write-Warning "uv 를 PATH 에서 못 찾았습니다. uv 설치 후 다시 실행하는 게 안전합니다."
}

# 창 없이(Hidden) run-worker.ps1 을 실행하는 작업
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
  -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$wrapper`""

# 이 사용자가 로그온할 때 시작
$trigger = New-ScheduledTaskTrigger -AtLogOn

# 배터리에서도 동작, 놓친 실행은 가능해지면 시작, 죽으면 1분 간격으로 재시작, 시간제한 없음
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
  -StartWhenAvailable -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
  -ExecutionTimeLimit ([TimeSpan]::Zero)

# 현재 사용자 계정으로, 로그온한 상태에서만 실행 (관리자 권한 불필요)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
  -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
  -Settings $settings -Principal $principal -Force | Out-Null

Write-Host "[OK] '$TaskName' 등록 완료 — 다음 로그온부터 자동 시작됩니다." -ForegroundColor Green
Write-Host "지금 바로 켜보려면:  Start-ScheduledTask -TaskName $TaskName"
Write-Host "돌고 있는지 로그 보기:  Get-Content data\worker.log -Wait"
Write-Host "끄려면:  Unregister-ScheduledTask -TaskName $TaskName -Confirm:`$false"
