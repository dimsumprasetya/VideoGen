@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
 "$d=[Environment]::GetFolderPath('Desktop');" ^
 "$s=(New-Object -ComObject WScript.Shell).CreateShortcut(\"$d\Seedance Studio.lnk\");" ^
 "$s.TargetPath='%~dp0studio.vbs';" ^
 "$s.WorkingDirectory='%~dp0';" ^
 "$s.IconLocation='%SystemRoot%\System32\imageres.dll,18';" ^
 "$s.Description='Seedance Studio';" ^
 "$s.Save()"
if errorlevel 1 (echo Gagal membuat shortcut.) else (echo Shortcut "Seedance Studio" dibuat di Desktop.)
pause
