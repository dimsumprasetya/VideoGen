@echo off
cd /d "%~dp0"
call findpy.bat
if not defined PY (pause & exit /b 1)
echo Menghentikan Seedance Studio...
call stop.bat >nul 2>&1
echo Mengambil versi terbaru dari GitHub...
rem Satu baris: file .bat ini bisa ikut diperbarui, jadi sisa perintah harus sudah dibaca cmd.
"%PY%" updater.py --now && (echo Menyalakan lagi... & wscript "%~dp0studio.vbs" & timeout /t 3 >nul & exit /b 0) || (echo Gagal update. Kirim pesan di atas ke Claude. & wscript "%~dp0studio.vbs" & pause & exit /b 1)
