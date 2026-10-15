@echo off
cd /d "%~dp0"
echo Menghentikan Seedance Studio...
call stop.bat >nul 2>&1
echo Mengambil versi terbaru...
rem Satu baris: file .bat ini ikut ditimpa saat update, jadi sisa perintah harus sudah dibaca cmd.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0update.ps1" %* && (echo Menyalakan lagi... & wscript "%~dp0studio.vbs" & echo Selesai. & timeout /t 3 >nul & exit /b 0) || (echo Gagal update. Kirim pesan di atas ke Claude. & pause & exit /b 1)
