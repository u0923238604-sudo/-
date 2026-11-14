@echo off
echo Scanning... (read-only, nothing will be deleted)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scan.ps1"
pause
