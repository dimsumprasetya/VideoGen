# Installer Seedance Studio (sekali jalan). Buka PowerShell lalu tempel:
#   irm https://raw.githubusercontent.com/dimsumprasetya/VideoGen/claude/focused-lovelace-y9fz03/install.ps1 | iex
# Memasang ke C:\AI\SeedanceStudio (ubah dengan $env:SEEDANCE_DIR), memindahkan data dari pemasangan lama,
# membuat shortcut Desktop + Start Menu + auto-start, memasang ffmpeg & Ollama (winget) bila belum ada,
# lalu menyalakan aplikasi. Setelah ini pembaruan berjalan otomatis.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$Repo = 'dimsumprasetya/VideoGen'
$Branch = 'claude/focused-lovelace-y9fz03'
$Dir = if ($env:SEEDANCE_DIR) { $env:SEEDANCE_DIR } else { 'C:\AI\SeedanceStudio' }
$Keep = @('studio_config.json', 'api_key.txt', 'python_path.txt')

function Say($m) { Write-Host $m -ForegroundColor Cyan }
function Ask($q) { $a = Read-Host "$q [Y/n]"; return ($a -eq '' -or $a -match '^[yY]') }
function RefreshPath { $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User') }
function HasWinget { return [bool](Get-Command winget -ErrorAction SilentlyContinue) }
function StopStudio($d) {
    $f = Join-Path $d 'studio.pids'
    if (Test-Path $f) {
        foreach ($p in ((Get-Content $f -Raw) -split '\s+' | Where-Object { $_ -match '^\d+$' })) {
            try { Stop-Process -Id ([int]$p) -Force -ErrorAction SilentlyContinue } catch {}
            try { cmd /c "taskkill /F /T /PID $p >nul 2>&1" } catch {}
        }
    }
}

Say "== Seedance Studio: pemasangan ke $Dir =="

# 1. Pemasangan lama (dari shortcut Desktop) -> hentikan, pindahkan datanya nanti
$desk = [Environment]::GetFolderPath('Desktop')
if (-not $desk) { $desk = Join-Path $HOME 'Desktop' }
$lnk = Join-Path $desk 'Seedance Studio.lnk'
$old = $null
if (Test-Path $lnk) {
    $t = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk).TargetPath
    if ($t -and (Test-Path $t)) { $old = Split-Path $t }
}
foreach ($d in @($old, $Dir)) { if ($d) { StopStudio $d } }

# 2. Unduh versi terbaru
Say "Mengunduh versi terbaru ($Branch)..."
$sha = (Invoke-RestMethod -Headers @{ Accept = 'application/vnd.github.sha'; 'User-Agent' = 'SeedanceStudio' } `
        -Uri "https://api.github.com/repos/$Repo/commits/$Branch").ToString().Trim()
$tmp = Join-Path $env:TEMP ('seedance-install-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory $tmp | Out-Null
$zip = Join-Path $tmp 'src.zip'
Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/$Repo/archive/$sha.zip" -OutFile $zip
Expand-Archive -Path $zip -DestinationPath (Join-Path $tmp 'x') -Force
$src = (Get-ChildItem (Join-Path $tmp 'x') -Directory | Select-Object -First 1).FullName
New-Item -ItemType Directory -Force $Dir | Out-Null
Get-ChildItem $src -Recurse -File | ForEach-Object {
    $rel = $_.FullName.Substring($src.Length + 1)
    $dst = Join-Path $Dir $rel
    if (($Keep -contains $rel) -and (Test-Path $dst)) { return }
    New-Item -ItemType Directory -Force (Split-Path $dst) | Out-Null
    Copy-Item $_.FullName $dst -Force
}
[IO.File]::WriteAllText((Join-Path $Dir 'version.txt'), $sha)
Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue

# 3. Data dari pemasangan lama
if ($old -and ((Resolve-Path $old).Path.TrimEnd('\') -ne (Resolve-Path $Dir).Path.TrimEnd('\'))) {
    Say "Memindahkan data dari $old ..."
    foreach ($sub in @('outputs', 'projects')) {
        $s = Join-Path $old $sub
        if (Test-Path $s) { New-Item -ItemType Directory -Force (Join-Path $Dir $sub) | Out-Null; Copy-Item (Join-Path $s '*') (Join-Path $Dir $sub) -Recurse -Force }
    }
    foreach ($f in $Keep) { $s = Join-Path $old $f; if (Test-Path $s) { Copy-Item $s (Join-Path $Dir $f) -Force } }
}

# 4. Python (sistem, atau python_embeded milik ComfyUI portable)
$py = $null
foreach ($c in @('python', 'py')) {
    try { $p = (& $c -c "import sys;print(sys.executable)" 2>$null); if ($LASTEXITCODE -eq 0 -and $p) { $py = $p.Trim(); break } } catch {}
}
if (-not $py) {
    foreach ($c in @('C:\AI\ComfyUI_windows_portable\python_embeded\python.exe', 'D:\AI\ComfyUI_windows_portable\python_embeded\python.exe')) {
        if (Test-Path $c) { $py = $c; break }
    }
}
if (-not $py -and (HasWinget) -and (Ask 'Python belum ada. Pasang Python 3.12 lewat winget?')) {
    winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
    RefreshPath
    try { $py = (& python -c "import sys;print(sys.executable)").Trim() } catch {}
}
if (-not $py) { throw 'Python tidak ditemukan. Pasang dari python.org lalu jalankan installer lagi.' }
[IO.File]::WriteAllText((Join-Path $Dir 'python_path.txt'), $py)
& $py -c "import json,sys;p=sys.argv[1];d=json.load(open(p,encoding='utf-8'));d['update_branch']=sys.argv[2];d.setdefault('auto_update',True);json.dump(d,open(p,'w',encoding='utf-8'),indent=2,ensure_ascii=False)" (Join-Path $Dir 'studio_config.json') $Branch
Say "Python: $py"

# 5. ffmpeg (untuk Editing/render)
RefreshPath
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    if ((HasWinget) -and (Ask 'ffmpeg belum ada (dibutuhkan untuk render video final). Pasang lewat winget?')) {
        winget install -e --id Gyan.FFmpeg --accept-source-agreements --accept-package-agreements
        RefreshPath
    } else { Write-Host 'Lewati ffmpeg. Pasang nanti dari https://www.gyan.dev/ffmpeg/builds/' -ForegroundColor Yellow }
}

# 6. Ollama (penulis ide/script/breakdown, gratis)
$ollamaExe = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
$hasOllama = (Get-Command ollama -ErrorAction SilentlyContinue) -or (Test-Path $ollamaExe)
if (-not $hasOllama -and (HasWinget) -and (Ask 'Ollama belum ada (penulis AI gratis). Pasang lewat winget?')) {
    winget install -e --id Ollama.Ollama --accept-source-agreements --accept-package-agreements
    RefreshPath
    $hasOllama = $true
}
if ($hasOllama) {
    $up = $false
    try { Invoke-RestMethod http://127.0.0.1:11434/api/version -TimeoutSec 3 | Out-Null; $up = $true } catch {}
    if (-not $up) {
        $appExe = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama app.exe'
        if (Test-Path $appExe) { Start-Process $appExe } else { Start-Process ollama -ArgumentList 'serve' -WindowStyle Hidden }
        for ($i = 0; $i -lt 30 -and -not $up; $i++) { Start-Sleep 1; try { Invoke-RestMethod http://127.0.0.1:11434/api/version -TimeoutSec 2 | Out-Null; $up = $true } catch {} }
    }
    $exe = if (Get-Command ollama -ErrorAction SilentlyContinue) { 'ollama' } else { $ollamaExe }
    $models = try { (Invoke-RestMethod http://127.0.0.1:11434/api/tags -TimeoutSec 5).models.name } catch { @() }
    if ($up -and -not ($models -match '^qwen3') -and (Ask 'Unduh model penulis qwen3:8b sekarang (~5 GB)?')) {
        & $exe pull qwen3:8b
        if ($LASTEXITCODE) { Write-Host 'Unduh qwen3:8b gagal. Bisa dicoba lagi dari aplikasi (Pengaturan > Penulis AI).' -ForegroundColor Yellow }
    }
    if (-not $up) { Write-Host 'Ollama belum menjawab; buka aplikasi Ollama sekali dari Start Menu.' -ForegroundColor Yellow }
}

# 7. Shortcut Desktop + Start Menu, auto-start
$sh = New-Object -ComObject WScript.Shell
$vbs = Join-Path $Dir 'studio.vbs'
foreach ($l in @($lnk, (Join-Path ([Environment]::GetFolderPath('Programs')) 'Seedance Studio.lnk'))) {
    $s = $sh.CreateShortcut($l); $s.TargetPath = $vbs; $s.WorkingDirectory = $Dir
    $s.IconLocation = "$env:SystemRoot\System32\imageres.dll,18"; $s.Description = 'Seedance Studio'; $s.Save()
}
$startup = Join-Path ([Environment]::GetFolderPath('Startup')) 'SeedanceStudio.vbs'
if (Ask 'Nyalakan Seedance Studio otomatis saat Windows mulai (disarankan, supaya update otomatis jalan)?') {
    $body = "Set sh = CreateObject(""WScript.Shell"")`r`nsh.CurrentDirectory = ""$Dir""`r`nsh.Run ""studio-start.bat --background"", 0, False`r`n"
    [IO.File]::WriteAllText($startup, $body)
} elseif (Test-Path $startup) { Remove-Item $startup }

# 8. Nyalakan
Say 'Menyalakan Seedance Studio...'
Start-Process wscript.exe -ArgumentList ('"' + $vbs + '"') -WorkingDirectory $Dir
Write-Host ''
Write-Host "Selesai. Terpasang di $Dir (versi $($sha.Substring(0,7)))." -ForegroundColor Green
Write-Host 'Buka lewat shortcut "Seedance Studio" di Desktop. Pembaruan dipasang otomatis.' -ForegroundColor Green
if ($old -and ((Resolve-Path $old).Path.TrimEnd('\') -ne (Resolve-Path $Dir).Path.TrimEnd('\'))) {
    Write-Host "Folder lama ($old) tidak dipakai lagi dan boleh dihapus setelah Anda cek." -ForegroundColor Yellow
}
