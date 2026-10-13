@echo off
set "S=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\SeedanceStudio.vbs"
> "%S%" echo Set sh = CreateObject("WScript.Shell")
>> "%S%" echo sh.CurrentDirectory = "%~dp0"
>> "%S%" echo sh.Run "pythonw studio.pyw --background", 0, False
echo Auto-start aktif.
pause
