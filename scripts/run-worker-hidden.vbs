' Launch run-worker.ps1 with NO console window at all.
' powershell -WindowStyle Hidden still flashes a console for a split second
' when Task Scheduler starts it in the interactive session; WScript.Shell.Run
' with window mode 0 never creates one. Used by the "jamak-worker-watch"
' scheduled task (every 5 min) and safe for the logon autostart too.
CreateObject("WScript.Shell").Run _
  "powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""C:\Projects\jamak-ouroboros\scripts\run-worker.ps1""", 0, False
