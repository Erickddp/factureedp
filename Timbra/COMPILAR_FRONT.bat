@echo off
chcp 65001 >nul
rem Solo si cambiaste el frontend (necesita Node.js 20+). Recompila y lo copia a backend\static
cd /d "%~dp0frontend"
where npm >nul 2>&1 || (echo [X] Instala Node.js LTS de https://nodejs.org & pause & exit /b 1)
call npm install
call npm run build || (echo [X] Fallo el build & pause & exit /b 1)
if exist "..\backend\static" rmdir /s /q "..\backend\static"
xcopy /e /i /q out "..\backend\static" >nul
echo [OK] Frontend compilado. Reinicia INICIAR.bat
pause
