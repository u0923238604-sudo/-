@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
python 監控程式.py --回測
pause
