@echo off
title Trading Terminal
color 0A
cd /d "%~dp0"
call venv\Scripts\activate.bat
echo Starting server...
echo Visit: http://localhost:5000
python app.py
pause
