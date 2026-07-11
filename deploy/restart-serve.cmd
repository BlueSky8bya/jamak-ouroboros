@echo off
REM 검수자 이름/비번(JAMAK_NAMES, JAMAK_PASSWORD) 바꾼 뒤 웹앱을 재시작해 반영.
REM 먼저:  setx JAMAK_NAMES "홍길동,김철수"   /   setx JAMAK_PASSWORD "새비번"
powershell -NoProfile -Command "$p=(Get-NetTCPConnection -LocalPort 8711 -State Listen -EA SilentlyContinue).OwningProcess; if($p){Stop-Process -Id $p -Force -EA SilentlyContinue}"
timeout /t 2 >nul
start "jamak-serve" /min "C:\Projects\asdf\deploy\start-serve.cmd"
echo 웹앱 재시작됨. jamak.hky-jamak.com 에 몇 초 뒤 반영.
