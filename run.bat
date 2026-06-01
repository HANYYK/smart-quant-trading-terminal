@echo off
chcp 65001 >nul
title Trading Terminal
color 0A

cd /d "D:\project\ruanjian project\ruanjian"

call venv\Scripts\activate.bat

echo.
echo Starting server...
echo Visit: http://localhost:5000
echo.

python app.py

pause
