@echo off
rem Pindahkan Seedance Studio (+ ComfyUI, model Ollama) ke drive lain, mis. G:
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0pindah-drive.ps1" %*
pause
