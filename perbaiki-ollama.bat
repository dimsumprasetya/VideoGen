@echo off
rem Perbaiki Ollama yang tidak mau menyala (hentikan sisa proses, bersihkan variabel salah, coba mode CPU).
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0perbaiki-ollama.ps1" %*
pause
