@echo off
echo === Proses ComfyUI yang sedang berjalan ===
powershell -NoProfile -Command "$p = Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'comfy' -or $_.CommandLine -match 'comfy' }; foreach ($x in $p) { $c = Get-NetTCPConnection -State Listen -OwningProcess $x.ProcessId -ErrorAction SilentlyContinue; foreach ($k in $c) { Write-Output ('PORT ' + $k.LocalPort + '  PID ' + $x.ProcessId + '  ' + $x.ExecutablePath + '  ' + $x.CommandLine) } }"
echo.
echo Kirim hasil di atas bila Seedance Studio belum tersambung.
pause
