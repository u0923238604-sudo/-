@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
title 加權指數 60分K 三刀流監控
python 監控程式.py
pause
