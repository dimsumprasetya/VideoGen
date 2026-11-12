# Memperbaiki Ollama yang "timed out waiting for server to start": hentikan sisa proses, bersihkan variabel salah,
# nyalakan server dengan log, coba mode CPU bila GPU bermasalah. Hasil lengkap disimpan di ollama-diag.txt.
param([switch]$NoPull)
$ErrorActionPreference = 'Continue'
$Out = Join-Path $PSScriptRoot 'ollama-diag.txt'
$log = New-Object System.Collections.ArrayList
function Say($m, $c = 'Cyan') { Write-Host $m -ForegroundColor $c; [void]$log.Add($m) }
function Alive { try { Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/version' -TimeoutSec 2 | Out-Null; return $true } catch { return $false } }

$exe = (Get-Command ollama -ErrorAction SilentlyContinue).Source
if (-not $exe) { $exe = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe' }
if (-not (Test-Path $exe)) { Say 'Ollama belum terpasang. Pasang: winget install Ollama.Ollama' 'Red'; return }
Say "Ollama: $exe"

# 1. Sisa proses
Say '1. Menghentikan proses Ollama yang menggantung...'
Get-Process -Name 'ollama*', 'ollama app' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep 2

# 2. Variabel lingkungan yang salah
Say '2. Memeriksa variabel lingkungan...'
foreach ($n in 'OLLAMA_MODELS', 'OLLAMA_HOST') {
    foreach ($scope in 'User', 'Machine') {
        $v = [Environment]::GetEnvironmentVariable($n, $scope)
        if (-not $v) { continue }
        Say "   $n ($scope) = $v"
        $bad = $false
        if ($n -eq 'OLLAMA_MODELS') {
            $root = try { [IO.Path]::GetPathRoot($v) } catch { $null }
            if (-not $root -or -not (Test-Path $root)) { $bad = $true }
        } else {
            if ($v -notmatch '^(https?://)?[\w\.\-]+(:\d+)?$') { $bad = $true }
        }
        if ($bad) {
            Say "   -> tidak valid / drive tidak ada, dihapus ($scope)." 'Yellow'
            try { [Environment]::SetEnvironmentVariable($n, $null, $scope) } catch { Say "   (butuh Admin untuk $scope)" 'Yellow' }
            Remove-Item "Env:$n" -ErrorAction SilentlyContinue
        }
    }
}

# 3. Port dipakai proses lain?
$c = Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue
if ($c) {
    $p = Get-Process -Id $c[0].OwningProcess -ErrorAction SilentlyContinue
    Say "3. Port 11434 dipakai: $($p.ProcessName) (PID $($c[0].OwningProcess))" 'Yellow'
    if ($p -and $p.ProcessName -notmatch 'ollama') { Say '   Tutup program itu atau ubah port Ollama (OLLAMA_HOST=127.0.0.1:11435).' 'Yellow' }
} else { Say '3. Port 11434 bebas.' }

function TryStart($label, $envs) {
    Say "4. Menyalakan server ($label)..."
    foreach ($k in $envs.Keys) { Set-Item "Env:$k" $envs[$k] }
    $so = Join-Path $env:TEMP 'ollama-out.txt'; $se = Join-Path $env:TEMP 'ollama-err.txt'
    Remove-Item $so, $se -ErrorAction SilentlyContinue
    $proc = Start-Process -FilePath $exe -ArgumentList 'serve' -WindowStyle Hidden -PassThru -RedirectStandardOutput $so -RedirectStandardError $se
    for ($i = 0; $i -lt 40; $i++) {
        Start-Sleep 1
        if (Alive) { Say "   Server hidup ($label)." 'Green'; return $true }
        if ($proc.HasExited) { break }
    }
    Say "   Gagal ($label)." 'Red'
    foreach ($f in $se, $so) { if (Test-Path $f) { Say "--- $f"; (Get-Content $f -Tail 25) | ForEach-Object { Say "   $_" 'Gray' } } }
    try { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue } catch {}
    Get-Process -Name 'ollama*' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep 2
    return $false
}

$ok = TryStart 'normal' @{}
$mode = 'normal'
if (-not $ok) { $ok = TryStart 'CPU saja (driver GPU dicurigai)' @{ CUDA_VISIBLE_DEVICES = '-1'; HIP_VISIBLE_DEVICES = '-1'; OLLAMA_LLM_LIBRARY = 'cpu' }; $mode = 'cpu' }

$sl = Join-Path $env:LOCALAPPDATA 'Ollama\server.log'
if (Test-Path $sl) { Say '--- server.log (30 baris akhir)'; (Get-Content $sl -Tail 30) | ForEach-Object { [void]$log.Add($_) } }
$log | Set-Content $Out -Encoding UTF8

if (-not $ok) {
    Say '' ; Say 'Ollama tetap gagal menyala. Kirim isi file ini ke pengembang:' 'Red'; Say "  $Out" 'Red'
    Say 'Langkah terakhir: winget install Ollama.Ollama --force  (pasang ulang), lalu jalankan skrip ini lagi.' 'Yellow'
    return
}
if ($mode -eq 'cpu') {
    Say 'Server hanya jalan di mode CPU: driver GPU (NVIDIA) perlu diperbarui. Mode CPU jauh lebih lambat, dan berlaku hanya untuk sesi ini.' 'Yellow'
}
$tags = try { (Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags').models.name } catch { @() }
if (-not $NoPull -and -not ($tags -contains 'qwen3:8b')) {
    $a = Read-Host 'Model qwen3:8b belum ada (~5 GB). Unduh sekarang? [Y/n]'
    if ($a -eq '' -or $a -match '^[yY]') { & $exe pull qwen3:8b }
}
Say 'Selesai. Muat ulang halaman Seedance Studio (http://127.0.0.1:7860).' 'Green'
