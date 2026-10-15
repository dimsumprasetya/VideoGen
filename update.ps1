# Update Seedance Studio: git pull bila folder ini clone git, selain itu unduh ZIP dari GitHub.
# Pakai: update.ps1 [nama-branch]   (default: branch utama repo)
$ErrorActionPreference = 'Stop'
$dir = $PSScriptRoot
$branch = if ($args.Count -gt 0) { $args[0] } else { 'HEAD' }

if ((Test-Path (Join-Path $dir '.git')) -and (Get-Command git -ErrorAction SilentlyContinue)) {
    Push-Location $dir
    try {
        $ErrorActionPreference = 'Continue'  # PS 5.1: stderr git jangan jadi error
        cmd /c "git checkout -- studio_config.json 2>nul"
        if ($branch -ne 'HEAD') { git fetch origin $branch; git checkout $branch }
        git pull
        if ($LASTEXITCODE) { throw 'git pull gagal' }
    } finally { Pop-Location }
    exit 0
}

$ProgressPreference = 'SilentlyContinue'  # progress bar membuat unduhan PS 5.1 sangat lambat
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$repo = 'https://github.com/dimsumprasetya/VideoGen/archive/'
$url = if ($branch -eq 'HEAD') { $repo + 'HEAD.zip' } else { $repo + 'refs/heads/' + $branch + '.zip' }
$tmp = Join-Path $env:TEMP ('seedance-update-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory $tmp | Out-Null
try {
    Write-Host "Mengunduh $url"
    $zip = Join-Path $tmp 'src.zip'
    Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $zip
    Expand-Archive -Path $zip -DestinationPath (Join-Path $tmp 'x') -Force
    $src = (Get-ChildItem (Join-Path $tmp 'x') -Directory | Select-Object -First 1).FullName
    # Jangan timpa pengaturan & data milik pengguna.
    $keep = @('studio_config.json', 'api_key.txt')
    $n = 0
    Get-ChildItem $src -Recurse -File | ForEach-Object {
        $rel = $_.FullName.Substring($src.Length + 1)
        $dst = Join-Path $dir $rel
        if (($keep -contains $rel) -and (Test-Path $dst)) { return }
        New-Item -ItemType Directory -Force (Split-Path $dst) | Out-Null
        Copy-Item $_.FullName $dst -Force
        $n++
    }
    Write-Host "$n file diperbarui."
} finally {
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
}
