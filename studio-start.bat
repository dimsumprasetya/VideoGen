@echo off
cd /d "%~dp0"
call findpy.bat
if not defined PY exit /b 1
"%PY%" studio.pyw %*
