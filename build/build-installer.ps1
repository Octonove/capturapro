# Genera el instalador unico CapturaPro-Setup-x.y.z.exe con Inno Setup.
# Si la carpeta dist no existe, compila antes la app con build.ps1.
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$distExe = Join-Path $root "dist\CapturaPro\CapturaPro.exe"

if (-not (Test-Path $distExe)) {
    Write-Host "== dist no encontrado: compilando la app primero ==" -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot "build.ps1")
}

Write-Host "== Localizando Inno Setup (ISCC) ==" -ForegroundColor Cyan
$iscc = (Get-Command iscc -ErrorAction SilentlyContinue).Source
if (-not $iscc) {
    $cands = @(
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    )
    $iscc = $cands | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $iscc) {
    Write-Host "ERROR: Inno Setup no encontrado. Instala con: winget install JRSoftware.InnoSetup --source winget" -ForegroundColor Red
    exit 1
}
Write-Host "ISCC: $iscc" -ForegroundColor Green

New-Item -ItemType Directory -Force -Path (Join-Path $root "installer") | Out-Null

Write-Host "== Compilando instalador ==" -ForegroundColor Cyan
& $iscc (Join-Path $PSScriptRoot "CapturaPro.iss")
$code = $LASTEXITCODE

if ($code -eq 0) {
    $out = Get-ChildItem (Join-Path $root "installer\CapturaPro-Setup-*.exe") -ErrorAction SilentlyContinue |
           Sort-Object LastWriteTime -Descending | Select-Object -First 1
    Write-Host "`n== LISTO ==" -ForegroundColor Green
    if ($out) { Write-Host ("Instalador: {0}  ({1} MB)" -f $out.FullName, [math]::Round($out.Length/1MB,1)) }
} else {
    Write-Host "`nLa compilacion del instalador fallo (codigo $code)." -ForegroundColor Red
    exit $code
}
