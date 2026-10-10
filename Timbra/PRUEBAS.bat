@echo off
chcp 65001 >nul
cd /d "%~dp0backend"
if not exist ".venv\Scripts\python.exe" (echo Primero corre INICIAR.bat una vez. & pause & exit /b 1)
".venv\Scripts\python.exe" -m pytest -q tests
pause
