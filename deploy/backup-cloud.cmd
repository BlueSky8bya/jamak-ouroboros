@echo off
REM Weekly cloud-DB backup. Snapshots the cloud Postgres to a local gzipped
REM SQLite file. Registered as a Windows scheduled task (jamak-backup-cloud).
REM
REM Reads two USER env vars (set once with setx, never hardcoded here so this
REM file stays secret-free / committable):
REM   DATABASE_URL      = the cloud Postgres URL (also used by `jamak run`)
REM   JAMAK_BACKUP_DIR  = output folder (e.g. a Google Drive path). Empty -> data\backups
REM (ASCII-only: Korean text breaks cmd.exe under a cp949 console.)
cd /d C:\Projects\asdf
uv run jamak backup-cloud --out "%JAMAK_BACKUP_DIR%" --keep 12
