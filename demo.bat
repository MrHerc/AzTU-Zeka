@echo off
rem Zeka - one-command demo (Windows): fresh demo data, server on http://127.0.0.1:5070, browser opens the 3-minute script.
cd /d "%~dp0"
echo Zeka demo: http://127.0.0.1:5070/?demo=1   (Ctrl+C - stop)
start "" cmd /c "timeout /t 2 >nul & start http://127.0.0.1:5070/?demo=1"
python run.py --reset --port 5070 || py -3 run.py --reset --port 5070
pause
