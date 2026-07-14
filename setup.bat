@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   ZOLO Auto CapCut - Setup
echo ============================================

if not exist venv (
    echo [1/2] Tao virtual environment...
    python -m venv venv
)

echo [2/2] Cai dat thu vien...
call venv\Scripts\activate.bat
pip install --upgrade pip
pip install -r requirements.txt
pip install -r capcut_mate_engine\requirements.txt

echo.
echo Setup xong. Chay run.bat (giao dien tkinter) hoac run_web.bat (giao dien web) de mo tool.
pause
