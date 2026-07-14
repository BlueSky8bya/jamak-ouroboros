# run-worker.ps1 — jamak worker 온디맨드 실행기 (감시자가 부른다)
#
# 동작 (2026-07-15, 사용자 결정 — "올리면 켜지고, 다 되면 꺼지고, 중복 없이"):
#   * 큐에 일이 있으면 워커가 처리하고, 큐가 비면 워커가 스스로 종료한다
#     (`jamak worker --until-idle`). 상시 기동 아님.
#   * 이 스크립트는 두 곳에서 불린다:
#       1) 로그온 시 Startup 폴더의 jamak-worker-autostart.vbs
#       2) 5분마다 스케줄드 태스크 "jamak-worker-watch"
#   * 중복 기동 방지는 2중: 아래 프로세스 검사(빠른 차단) + 워커 자신의
#     OS 네임드 뮤텍스(Global\jamak-worker-singleton — 경합 완전 차단).
# 수동으로 상시 워커를 원하면 기존처럼:  uv run jamak worker
$ErrorActionPreference = "Continue"

# 프로젝트 루트 = 이 스크립트(scripts\)의 부모 폴더
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

# ANTHROPIC_API_KEY / DATABASE_URL 이 세션에 없으면 User 레지스트리에서 가져온다.
foreach ($k in @("ANTHROPIC_API_KEY", "DATABASE_URL")) {
  if (-not (Get-Item "env:$k" -ErrorAction SilentlyContinue)) {
    try {
      $v = (Get-ItemProperty HKCU:\Environment -ErrorAction Stop).$k
      if ($v) { Set-Item "env:$k" $v }
    } catch {}
  }
}
$env:PYTHONIOENCODING = "utf-8"

# uv 를 PATH 에서 못 찾으면 흔한 설치 위치를 시도
$uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
if (-not $uv) {
  foreach ($p in @("$env:USERPROFILE\.local\bin\uv.exe",
                   "$env:LOCALAPPDATA\Microsoft\WinGet\Links\uv.exe")) {
    if (Test-Path $p) { $uv = $p; break }
  }
}
if (-not $uv) { $uv = "uv" }

$log = Join-Path $ProjectRoot "data\worker.log"
New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null

# 이미 워커가 떠 있으면 그대로 둔다 (그 워커가 큐를 다 비우고 스스로 꺼짐)
$mine = $PID
$running = Get-CimInstance Win32_Process -Filter "Name like '%python%'" -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -like '*jamak*worker*' -and $_.ProcessId -ne $mine }
if ($running) { return }

"[$(Get-Date -Format s)] jamak worker 기동 (until-idle, uv=$uv)" | Out-File -FilePath $log -Append -Encoding utf8
& $uv run jamak worker --until-idle *>> $log
"[$(Get-Date -Format s)] jamak worker 종료 (exit=$LASTEXITCODE)" | Out-File -FilePath $log -Append -Encoding utf8
