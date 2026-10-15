# Buka firewall Windows untuk Seedance Studio, KHUSUS dari jaringan Tailscale (100.64.0.0/10).
# Dijalankan sebagai administrator lewat izinkan-akses-hp.bat (atau installer).
param([switch]$NoPause)
$ErrorActionPreference = 'Continue'
$dir = $PSScriptRoot
$port = 7860
try { $port = [int]((Get-Content (Join-Path $dir 'studio_config.json') -Raw | ConvertFrom-Json).app_port) } catch {}
$name = 'Seedance Studio (Tailscale)'
Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName $name -Direction Inbound -Action Allow -Protocol TCP -LocalPort $port `
    -RemoteAddress 100.64.0.0/10 -Profile Any | Out-Null
Write-Host "Port $port dibuka hanya untuk perangkat Tailscale (100.64.0.0/10)."

# Bila dulu jendela peringatan firewall untuk python ditutup dengan "Cancel/Batal", Windows membuat aturan
# BLOKIR untuk python.exe yang mengalahkan izin di atas. Hapus hanya aturan blokir untuk Python milik aplikasi ini.
$py = 'python.exe'
$pf = Join-Path $dir 'python_path.txt'
if (Test-Path $pf) { $py = (Get-Content $pf -Raw).Trim() }
Get-NetFirewallRule -Direction Inbound -Action Block -ErrorAction SilentlyContinue | ForEach-Object {
    $prog = ($_ | Get-NetFirewallApplicationFilter).Program
    if ($prog -and (($prog -ieq $py) -or ((Split-Path $py -Leaf) -ieq 'python.exe' -and $py -notmatch '\\' -and $prog -match 'python'))) {
        Write-Host ('Hapus aturan blokir: ' + $_.DisplayName + ' (' + $prog + ')')
        Remove-NetFirewallRule -InputObject $_
    }
}
if (-not $NoPause) { Read-Host 'Selesai. Tekan Enter untuk menutup' | Out-Null }
