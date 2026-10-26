@echo off
rem RustDesk one-click installer: runs install_rustdesk.ps1 in the same folder
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_rustdesk.ps1"
