@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
echo 正在安裝必要套件（只需執行一次）...
python -m pip install --upgrade pandas requests plyer
echo.
echo 安裝完成！接著請執行「測試通知.bat」。
pause
