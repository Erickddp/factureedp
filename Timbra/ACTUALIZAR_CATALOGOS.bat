@echo off
chcp 65001 >nul
rem Actualiza satcfdi: catalogos del SAT (claves, CP, regimenes) y conexion con los PAC.
rem Correlo cuando el SAT publique cambios en el Anexo 20 (normalmente en enero).
cd /d "%~dp0backend"
if not exist ".venv\Scripts\python.exe" (echo Primero corre INICIAR.bat una vez. & pause & exit /b 1)
".venv\Scripts\python.exe" -m pip install --upgrade satcfdi
".venv\Scripts\python.exe" -c "import importlib.metadata as m; print('satcfdi', m.version('satcfdi'))"
echo [OK] Catalogos actualizados. Cierra y vuelve a abrir INICIAR.bat
pause
