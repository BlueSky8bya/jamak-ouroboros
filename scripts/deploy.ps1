# deploy.ps1
# 현재 변경사항을 커밋하고 origin 에 푸시 → Railway 가 자동 재배포한다.
# 사용:
#   powershell -ExecutionPolicy Bypass -File scripts\deploy.ps1 "커밋 메시지"
# 메시지를 생략하면 기본 메시지로 커밋한다.

param([string]$Message = "deploy: update")

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

git add -A

$staged = git diff --cached --name-only
if (-not $staged) {
  Write-Host "커밋할 변경이 없습니다. (이미 다 올라갔거나 수정이 없음)" -ForegroundColor Yellow
  exit 0
}

Write-Host "커밋에 포함될 파일:" -ForegroundColor Cyan
$staged | ForEach-Object { Write-Host "  $_" }

git commit -m $Message | Out-Null
git push

$sha = (git rev-parse --short HEAD)
Write-Host ""
Write-Host "[OK] 푸시 완료 — 배포 커밋: $sha" -ForegroundColor Green
Write-Host "Railway 배포가 끝나면 사이트 헤더가 '배포 $sha' 로 바뀌면 반영 완료입니다."
Write-Host "확인: https://hky-jamak.com/api/version"
