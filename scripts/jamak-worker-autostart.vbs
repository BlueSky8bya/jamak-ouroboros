' jamak subtitle worker — logon autostart, fully hidden (no console flash).
'
' Install: copy this file into the user's Startup folder
'   %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
' It launches run-worker.ps1 (which has the restart loop + dedup guard).
'
' Replaces the older jamak-worker-autostart.cmd, which flashed a console
' window on every boot. WScript.Shell.Run with window mode 0 shows nothing.
' Remove the copy in the Startup folder to disable autostart.
CreateObject("WScript.Shell").Run "powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""C:\Projects\jamak-ouroboros\scripts\run-worker.ps1""", 0, False
