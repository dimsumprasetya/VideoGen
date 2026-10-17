# Memindahkan Seedance Studio (dan opsional ComfyUI + model Ollama) ke drive lain, mis. G:.
# Pakai: pindah-drive.bat  (atau: powershell -File pindah-drive.ps1 -Drive G -Comfy -Ollama)
# Folder lama TIDAK dihapus otomatis; hapus sendiri setelah Anda cek semuanya jalan.
param([string]$Drive = '', [switch]$Comfy, [switch]$Ollama, [switch]$Yes)
$ErrorActionPreference = 'Stop'
function Say($m) { Write-Host $m -ForegroundColor Cyan }
function Ask($q) { if ($Yes) { return $true }; return ((Read-Host "$q [Y/n]") -notmatch '^[nN]') }
function Norm($p) { return [IO.Path]::GetFullPath($p).TrimEnd('\') }

$Src = Norm $PSScriptRoot
if (-not $Drive) { $Drive = Read-Host 'Pindah ke drive apa? (contoh: G)' }
$Drive = $Drive.Trim().TrimEnd(':', '\').ToUpper()
if ($Drive.Length -ne 1 -or -not (Test-Path "${Drive}:\")) { throw "Drive ${Drive}: tidak ditemukan. Colokkan SSD-nya dulu." }
$Root = "${Drive}:\AI"
$Dst = Join-Path $Root 'SeedanceStudio'
if ((Norm $Dst) -eq $Src) { throw 'Aplikasi sudah ada di lokasi tujuan.' }
if (-not $PSBoundParameters.ContainsKey('Comfy')) { $Comfy = [bool](Ask 'Pindahkan ComfyUI portable juga (model besar, biasanya puluhan GB)?') }
if (-not $PSBoundParameters.ContainsKey('Ollama')) { $Ollama = [bool](Ask 'Pindahkan model Ollama juga (qwen3:8b ~5 GB)?') }

function SizeGB($p) { if (-not (Test-Path $p)) { return 0 }; return [math]::Round(((Get-ChildItem $p -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum / 1GB), 1) }

# Baca konfigurasi sekarang
$cfgPath = Join-Path $Src 'studio_config.json'
$cfg = if (Test-Path $cfgPath) { Get-Content $cfgPath -Raw | ConvertFrom-Json } else { [pscustomobject]@{} }
$comfySrc = $null
if ($cfg.comfy_cwd -and (Test-Path $cfg.comfy_cwd)) { $comfySrc = Norm $cfg.comfy_cwd }
elseif (Test-Path 'C:\AI\ComfyUI_windows_portable') { $comfySrc = 'C:\AI\ComfyUI_windows_portable' }
$comfyInside = $comfySrc -and $comfySrc.StartsWith($Src + '\')
$ollamaSrc = if ($env:OLLAMA_MODELS) { $env:OLLAMA_MODELS } else { Join-Path $HOME '.ollama\models' }

$need = SizeGB $Src
if ($Comfy -and $comfySrc -and -not $comfyInside) { $need += SizeGB $comfySrc }
if ($Ollama -and (Test-Path $ollamaSrc)) { $need += SizeGB $ollamaSrc }
$free = [math]::Round((Get-PSDrive $Drive).Free / 1GB, 1)
Say "Perlu ~$need GB, ruang kosong di ${Drive}: $free GB."
if ($free -lt ($need + 2)) { throw 'Ruang di drive tujuan tidak cukup.' }
if (-not (Ask "Mulai memindahkan ke $Root ?")) { return }

# 1. Hentikan aplikasi (dan ComfyUI yang dinyalakan supervisor)
Say 'Menghentikan Seedance Studio...'
try { & (Join-Path $Src 'stop.bat') | Out-Null } catch {}
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $_.Name -match '^(python|pythonw|wscript)(\.exe)?$' -and $_.CommandLine -and ($_.CommandLine -like "*$Src*" -or ($Comfy -and $comfySrc -and $_.CommandLine -like "*$comfySrc*")) -and $_.ProcessId -ne $PID
} | ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force } catch {} }
Start-Sleep 2

function Copy-Tree($from, $to) {
    New-Item -ItemType Directory -Force $to | Out-Null
    & robocopy $from $to /E /COPY:DAT /R:2 /W:2 /NFL /NDL /NP /XD __pycache__ | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "Salin gagal: $from -> $to (robocopy $LASTEXITCODE)" }
}

# 2. Salin aplikasi (proyek, hasil video, serial, cache ikut)
Say "Menyalin aplikasi ke $Dst ..."
Copy-Tree $Src $Dst

# 3. ComfyUI portable
$comfyDst = $null
if ($Comfy -and $comfySrc) {
    if ($comfyInside) { $comfyDst = Join-Path $Dst $comfySrc.Substring($Src.Length + 1) }
    else {
        $comfyDst = Join-Path $Root (Split-Path $comfySrc -Leaf)
        Say "Menyalin ComfyUI ke $comfyDst (bisa lama)..."
        Copy-Tree $comfySrc $comfyDst
    }
}

# 4. Model Ollama
if ($Ollama -and (Test-Path $ollamaSrc)) {
    $od = Join-Path $Root 'ollama\models'
    Say "Menyalin model Ollama ke $od ..."
    Copy-Tree $ollamaSrc $od
    [Environment]::SetEnvironmentVariable('OLLAMA_MODELS', $od, 'User')
    Get-Process ollama*, 'ollama app' -ErrorAction SilentlyContinue | Stop-Process -Force
    Say 'OLLAMA_MODELS diatur. Ollama dinyalakan ulang otomatis oleh app; bila belum, buka ulang Ollama.'
}

# 5. Perbaiki path di konfigurasi baru
$cfgDst = Join-Path $Dst 'studio_config.json'
function Fix($text) {
    $t = $text.Replace($Src, $Dst).Replace($Src.Replace('\', '\\'), $Dst.Replace('\', '\\'))
    if ($comfyDst -and $comfySrc) { $t = $t.Replace($comfySrc, $comfyDst).Replace($comfySrc.Replace('\', '\\'), $comfyDst.Replace('\', '\\')) }
    return $t
}
if (Test-Path $cfgDst) { [IO.File]::WriteAllText($cfgDst, (Fix (Get-Content $cfgDst -Raw))) }
$pyf = Join-Path $Dst 'python_path.txt'
if (Test-Path $pyf) { [IO.File]::WriteAllText($pyf, (Fix (Get-Content $pyf -Raw)).Trim()) }

# 6. Shortcut, Start Menu, auto-start
$sh = New-Object -ComObject WScript.Shell
$vbs = Join-Path $Dst 'studio.vbs'
$desk = [Environment]::GetFolderPath('Desktop')
foreach ($l in @((Join-Path $desk 'Seedance Studio.lnk'), (Join-Path ([Environment]::GetFolderPath('Programs')) 'Seedance Studio.lnk'))) {
    $s = $sh.CreateShortcut($l); $s.TargetPath = $vbs; $s.WorkingDirectory = $Dst
    $s.IconLocation = "$env:SystemRoot\System32\imageres.dll,18"; $s.Description = 'Seedance Studio'; $s.Save()
}
$startup = Join-Path ([Environment]::GetFolderPath('Startup')) 'SeedanceStudio.vbs'
if (Test-Path $startup) {
    $body = "Set sh = CreateObject(""WScript.Shell"")`r`nsh.CurrentDirectory = ""$Dst""`r`nsh.Run ""studio-start.bat --background"", 0, False`r`n"
    [IO.File]::WriteAllText($startup, $body)
}

# 7. Nyalakan dari lokasi baru
Say 'Menyalakan dari lokasi baru...'
Start-Process wscript.exe -ArgumentList ('"' + $vbs + '"') -WorkingDirectory $Dst
Write-Host ''
Write-Host "Selesai. Seedance Studio sekarang di $Dst." -ForegroundColor Green
if ($comfyDst) { Write-Host "ComfyUI sekarang di $comfyDst. Aplikasi lain yang memakainya (mis. Luminar Studio) harus diarahkan ke path baru." -ForegroundColor Yellow }
Write-Host 'Bila akses dari HP aktif, jalankan ulang izinkan-akses-hp.bat (aturan firewall mengacu ke python lama).' -ForegroundColor Yellow
Write-Host "Setelah yakin semuanya jalan, hapus folder lama: $Src" -ForegroundColor Yellow
