@echo off
chcp 65001 >nul
rem Modo desarrollo: backend con recarga + frontend con recarga en http://localhost:3000
cd /d "%~dp0backend"
start "Timbra API" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000"
cd /d "%~dp0frontend"
if not exist node_modules call npm install
start "Timbra Web" cmd /k "npm run dev"
timeout /t 6 >nul
start "" http://localhost:3000
