# run-worker.ps1
# jamak 자막 worker를 실행한다. 'jamak-worker' 작업(로그온 자동시작)이 이 파일을 부른다.
# 수동으로 한 번 켜보고 싶으면:  powershell -ExecutionPolicy Bypass -File scripts\run-worker.ps1
$ErrorActionPreference = "Continue"

# 프로젝트 루트 = 이 스크립트(scripts\)의 부모 폴더
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

# ANTHROPIC_API_KEY / DATABASE_URL 이 세션에 없으면 User 레지스트리에서 가져온다.
# (로그온 자동시작이 아니라 다른 경로로 실행될 때도 클라우드 큐에 붙도록 — 워커는
#  클라우드 Postgres 를 폴링해야 하므로 DATABASE_URL 이 없으면 로컬 SQLite 를 봐서
#  대기열을 못 본다.)
foreach ($k in @("ANTHROPIC_API_KEY", "DATABASE_URL")) {
  if (-not (Get-Item "env:$k" -ErrorAction SilentlyContinue)) {
    try {
      $v = (Get-ItemProperty HKCU:\Environment -ErrorAction Stop).$k
      if ($v) { Set-Item "env:$k" $v }
    } catch {}
  }
}
# 콘솔 인코딩 (한글 안전)
$env:PYTHONIOENCODING = "utf-8"

# uv 를 PATH 에서 못 찾으면 흔한 설치 위치를 시도
$uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
if (-not $uv) {
  foreach ($p in @("$env:USERPROFILE\.local\bin\uv.exe",
                   "$env:LOCALAPPDATA\Microsoft\WinGet\Links\uv.exe")) {
    if (Test-Path $p) { $uv = $p; break }
  }
}
if (-not $uv) { $uv = "uv" }  # 마지막 시도: 그냥 uv

# 로그 파일에 표준출력/에러를 남긴다 (백그라운드라 창이 안 보이므로).
# 실시간으로 보려면:  Get-Content data\worker.log -Wait
$log = Join-Path $ProjectRoot "data\worker.log"
New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null

# 이미 워커가 떠 있으면 두 번 켜지 않는다 (하나의 8GB GPU 는 동시 두 영상 처리 불가).
$mine = $PID
$running = Get-CimInstance Win32_Process -Filter "Name like '%python%'" -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -like '*jamak*worker*' -and $_.ProcessId -ne $mine }
if ($running) {
  "[$(Get-Date -Format s)] jamak worker 이미 실행 중 (PID $($running.ProcessId -join ',')) — 중복 실행 안 함" |
    Out-File -FilePath $log -Append -Encoding utf8
  return
}

# 자동 재시작 루프: 워커가 예기치 않게 죽어도(크래시/일시적 DB 단절) 사람 손 없이
# 다시 뜬다. 짧은 백오프 뒤 재시작. 로그온 자동시작이 이 스크립트를 한 번 부르면,
# 이후로는 이 루프가 워커를 계속 살려둔다 (사용자가 명령을 직접 칠 일이 없다).
# (정상 종료도 재시작하지만, 워커는 Ctrl+C 전까지 스스로 끝나지 않으므로 문제 없음.)
while ($true) {
  "[$(Get-Date -Format s)] jamak worker 시작 (uv=$uv)" | Out-File -FilePath $log -Append -Encoding utf8
  & $uv run jamak worker *>> $log
  $code = $LASTEXITCODE
  "[$(Get-Date -Format s)] jamak worker 종료 (exit=$code), 10초 후 재시작" |
    Out-File -FilePath $log -Append -Encoding utf8
  Start-Sleep -Seconds 10
}
