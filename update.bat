@echo off
cd /d "%~dp0"
echo Menghentikan Seedance Studio...
call stop.bat >nul 2>&1
echo Mengambil versi terbaru...
git checkout -- studio_config.json >nul 2>&1
git pull
if errorlevel 1 (echo Gagal update. Kirim pesan di atas ke Claude. & pause & exit /b 1)
echo Menyalakan lagi...
wscript "%~dp0studio.vbs"
echo Selesai.
timeout /t 3 >nul
