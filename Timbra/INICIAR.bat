@echo off
chcp 65001 >nul
title Timbra - Facturacion CFDI 4.0
cd /d "%~dp0backend"

echo.
echo  ===============================================
echo    TIMBRA - arrancando, no cierres esta ventana
echo  ===============================================
echo.

rem --- 1. Buscar Python -------------------------------------------------
set "PY="
py -3.12 --version >nul 2>&1 && set "PY=py -3.12"
if not defined PY py -3 --version >nul 2>&1 && set "PY=py -3"
if not defined PY python --version >nul 2>&1 && set "PY=python"
if not defined PY goto :sinpython

rem --- 2. Entorno virtual (solo la primera vez) -------------------------
if not exist ".venv\Scripts\python.exe" (
  echo [1/3] Creando entorno de Python, tarda poquito...
  %PY% -m venv .venv
  if errorlevel 1 goto :error
)
set "VPY=.venv\Scripts\python.exe"

rem --- 3. Dependencias (solo si cambiaron) ------------------------------
fc /b requirements.txt ".venv\req_instalados.txt" >nul 2>&1
if errorlevel 1 (
  echo [2/3] Instalando dependencias, la primera vez tarda 2-5 minutos...
  "%VPY%" -m pip install --upgrade pip -q
  "%VPY%" -m pip install -r requirements.txt -q
  if errorlevel 1 goto :error
  copy /y requirements.txt ".venv\req_instalados.txt" >nul
)

rem --- 4. Preparar (.env, carpeta datos, puerto) ------------------------
"%VPY%" preparar.py
if errorlevel 2 (
  start "" http://localhost:8000
  exit /b 0
)
if errorlevel 1 goto :error

rem --- 5. Abrir navegador y arrancar ------------------------------------
echo [3/3] Abriendo http://localhost:8000
echo       Usuario inicial: el ADMIN_EMAIL de backend\.env  /  contrasena: cambiame  (cambiala en Ajustes)
echo       Para apagar Timbra cierra esta ventana.
echo.
start "" cmd /c "timeout /t 5 >nul & start http://localhost:8000"
"%VPY%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
goto :eof

:sinpython
echo [X] No encontre Python en esta computadora.
echo     Voy a intentar instalarlo con winget (Python 3.12)...
winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
echo.
echo     Si se instalo bien: CIERRA esta ventana y vuelve a abrir INICIAR.bat
echo     Si no: descargalo de https://www.python.org/downloads/ y marca "Add python.exe to PATH".
pause
exit /b 1

:error
echo.
echo [X] Algo fallo. Toma foto de esta ventana y pasasela a Claude.
pause
exit /b 1
