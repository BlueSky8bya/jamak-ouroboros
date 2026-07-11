# run-worker.ps1
# jamak 자막 worker를 실행한다. 'jamak-worker' 작업(로그온 자동시작)이 이 파일을 부른다.
# 수동으로 한 번 켜보고 싶으면:  powershell -ExecutionPolicy Bypass -File scripts\run-worker.ps1
$ErrorActionPreference = "Continue"

# 프로젝트 루트 = 이 스크립트(scripts\)의 부모 폴더
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

# ANTHROPIC_API_KEY 가 세션에 없으면 User 레지스트리에서 가져온다 (CLAUDE.md 규칙)
if (-not $env:ANTHROPIC_API_KEY) {
  try { $env:ANTHROPIC_API_KEY = (Get-ItemProperty HKCU:\Environment -ErrorAction Stop).ANTHROPIC_API_KEY } catch {}
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
"[$(Get-Date -Format s)] jamak worker 시작 (uv=$uv)" | Out-File -FilePath $log -Append -Encoding utf8

& $uv run jamak worker *>> $log
