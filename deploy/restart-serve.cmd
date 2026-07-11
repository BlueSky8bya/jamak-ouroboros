@echo off
REM Restart the review web app after changing JAMAK_NAMES / JAMAK_PASSWORD etc.
REM First:  setx JAMAK_NAMES "name1,name2"   /   setx JAMAK_PASSWORD "newpw"
REM (ASCII-only on purpose: Korean text here breaks cmd.exe under a cp949 console.)
powershell -NoProfile -Command "$p=(Get-NetTCPConnection -LocalPort 8711 -State Listen -EA SilentlyContinue).OwningProcess; if($p){Stop-Process -Id $p -Force -EA SilentlyContinue}"
timeout /t 2 >nul
start "jamak-serve" /min "C:\Projects\asdf\deploy\start-serve.cmd"
echo Web app restarted. jamak.hky-jamak.com updates in a few seconds.
