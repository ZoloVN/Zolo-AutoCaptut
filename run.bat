@echo off
chcp 65001 >nul
cd /d "%~dp0"
call venv\Scripts\activate.bat
python zolo_autocapcut_gui.py
pause
