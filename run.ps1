# Ejecuta CapturaPro en modo desarrollo (sin compilar).
$root = $PSScriptRoot
$pyw = Join-Path $root ".venv\Scripts\pythonw.exe"
$py  = Join-Path $root ".venv\Scripts\python.exe"
if (Test-Path $pyw) {
    & $pyw (Join-Path $root "CapturaPro.py")
} elseif (Test-Path $py) {
    & $py (Join-Path $root "CapturaPro.py")
} else {
    & python (Join-Path $root "CapturaPro.py")
}
