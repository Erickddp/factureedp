@echo off
chcp 65001 >nul
title Timbra - construir instalador
rem Genera instalador\salida\Timbra-Instalador-2.8.0.exe (un solo archivo para cualquier PC con Windows 10/11).
rem Requiere haber corrido INICIAR.bat una vez. Si cambiaste el front, corre antes COMPILAR_FRONT.bat.
cd /d "%~dp0backend"
if not exist ".venv\Scripts\python.exe" (echo Primero corre INICIAR.bat una vez. & pause & exit /b 1)

echo [1/4] Pruebas (no se empaqueta nada que no pase)...
".venv\Scripts\python.exe" -m pytest -q tests || (echo [X] Fallaron las pruebas. & pause & exit /b 1)

echo [2/4] Herramientas de empaquetado...
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt pyinstaller pystray pillow || goto :error

echo [3/4] Empaquetando Timbra.exe...
".venv\Scripts\python.exe" -m PyInstaller timbra.spec --noconfirm --clean || goto :error

echo [4/4] Armando el instalador...
set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
  echo     Instalando Inno Setup con winget...
  winget install -e --id JRSoftware.InnoSetup --accept-package-agreements --accept-source-agreements
  set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
  if not exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
)
"%ISCC%" "%~dp0instalador\timbra.iss" || goto :error

echo.
echo [OK] Instalador listo: %~dp0instalador\salida\
explorer "%~dp0instalador\salida"
pause
exit /b 0

:error
echo [X] Algo fallo. Toma foto de esta ventana y pasasela a Claude.
pause
exit /b 1
