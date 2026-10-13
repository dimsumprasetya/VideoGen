@echo off
rem Cari Python: 1) python_path.txt  2) Python sistem yang sungguhan  3) python_embeded milik ComfyUI portable
set "PY="
if exist "%~dp0python_path.txt" set /p PY=<"%~dp0python_path.txt"
if defined PY if exist "%PY%" goto :eof
set "PY="
python -c "import sys" >nul 2>&1 && set "PY=python"
if defined PY goto :eof
for %%E in ("C:\AI\ComfyUI_windows_portable\python_embeded\python.exe" "D:\AI\ComfyUI_windows_portable\python_embeded\python.exe") do (
  if exist %%E if not defined PY set "PY=%%~E"
)
if not defined PY (
  echo Python tidak ditemukan. Pasang Python 3 dari python.org, atau tulis path python.exe di file python_path.txt
)
goto :eof
