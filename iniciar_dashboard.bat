@echo off
setlocal
cd /d "%~dp0"
echo.
echo ================================================
echo   SDDTrack Dashboard - inicializacao local
echo ================================================
echo Pasta utilizada: %CD%
echo.
python dashboard.py
if errorlevel 1 (
  echo.
  echo Nao foi possivel iniciar. Verifique se Python 3 esta instalado e tente novamente.
  pause
)
endlocal
