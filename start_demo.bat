@echo off
cd /d "%~dp0"
echo AzTU Reqemsal Kampus demo: http://127.0.0.1:5070
echo Dayandirmaq ucun bu pencereni baglayin (ve ya Ctrl+C).
start "" http://127.0.0.1:5070/
python run.py --port 5070 || py -3 run.py --port 5070
pause
