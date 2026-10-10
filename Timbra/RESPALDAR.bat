@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist Respaldos mkdir Respaldos
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmm"') do set "F=%%i"
echo Respaldando datos (base de datos, XML timbrados) y llaves (.env)...
powershell -NoProfile -Command "Compress-Archive -Path 'backend\datos','backend\.env' -DestinationPath 'Respaldos\timbra_%F%.zip' -Force"
if errorlevel 1 (echo [X] No se pudo respaldar. & pause & exit /b 1)
echo [OK] Respaldo en Respaldos\timbra_%F%.zip  -- subelo a tu Drive.
pause
