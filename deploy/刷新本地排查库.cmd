@echo off
python "%~dp0refresh-local-debug.py" %*
if errorlevel 1 (
  pause
  exit /b 1
)
pause
