@echo off
REM Cloudflare 고정 터널 (jamak.hky-jamak.com -> 127.0.0.1:8711)
"C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel run jamak
