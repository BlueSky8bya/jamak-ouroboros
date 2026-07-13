@echo off
REM 검수 웹앱 (포트 8711). JAMAK_AUTH는 사용자 환경변수에서 읽음.
cd /d C:\Projects\jamak-ouroboros
uv run jamak serve --port 8711
