@echo off
cd /d "%~dp0"
call findpy.bat
if not defined PY (pause & exit /b 1)
"%PY%" app.py
pause
