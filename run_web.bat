@echo off
chcp 65001 >nul
cd /d "%~dp0"
call venv\Scripts\activate.bat

echo ============================================
echo   ZOLO Auto CapCut - Web UI
echo ============================================
echo Dang khoi dong capcut_mate_engine (tra cuu sticker/effect cuc bo, cong 30000)...
start "capcut_mate_engine" /min venv\Scripts\python.exe capcut_mate_engine\main.py

timeout /t 2 /nobreak >nul

echo Dang khoi dong ZOLO server (giao dien chinh, cong 5757)...
start "" http://127.0.0.1:5757
python server.py

echo.
echo Da dong ZOLO server. Neu capcut_mate_engine (cua so "capcut_mate_engine") van con
echo chay ngam, dong tay cua so do de giai phong cong 30000.
pause
