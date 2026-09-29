$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "Atamation tek-exe paketi hazirlaniyor..."

$vendor = Join-Path $PSScriptRoot "vendor\ffmpeg"
if (-not (Test-Path (Join-Path $vendor "ffmpeg.exe"))) {
    Write-Host "vendor\ffmpeg bulunamadi. Essentials FFmpeg indiriliyor..."
    $zip = Join-Path $env:TEMP "ffmpeg-essentials.zip"
    $url = "https://github.com/GyanD/codexffmpeg/releases/download/7.1.1/ffmpeg-7.1.1-essentials_build.zip"
    New-Item -ItemType Directory -Force -Path $vendor | Out-Null
    Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
    $extract = Join-Path $env:TEMP "ffmpeg-essentials-extract"
    if (Test-Path $extract) { Remove-Item $extract -Recurse -Force }
    Expand-Archive -Path $zip -DestinationPath $extract -Force
    $bin = Get-ChildItem -Path $extract -Recurse -Filter "ffmpeg.exe" | Select-Object -First 1
    if (-not $bin) { throw "ffmpeg.exe arsivde yok" }
    Copy-Item $bin.FullName (Join-Path $vendor "ffmpeg.exe") -Force
    $probe = Join-Path $bin.Directory.FullName "ffprobe.exe"
    if (Test-Path $probe) { Copy-Item $probe (Join-Path $vendor "ffprobe.exe") -Force }
}

python -m pip install -r requirements.txt pyinstaller pywebview
python -m PyInstaller --noconfirm --clean atamation.spec

$exe = Join-Path $PSScriptRoot "dist\AtamationDownloader.exe"
if (-not (Test-Path $exe)) {
    throw "PyInstaller tek exe uretemedi: $exe"
}

$sizeMb = [math]::Round((Get-Item $exe).Length / 1MB, 1)
Write-Host "Hazir: $exe ($sizeMb MB)"
Write-Host "Bu tek dosyayi baska bilgisayara kopyalayip calistirabilirsiniz."
