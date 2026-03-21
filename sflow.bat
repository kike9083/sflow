@echo off
cd /d "%~dp0"
echo Iniciando sflow...
"venv\Scripts\python.exe" "main.py"
if errorlevel 1 pause