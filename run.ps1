$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$database = Join-Path $backend "data\career_quest.db"

if (-not (Test-Path -LiteralPath $database)) {
    & python (Join-Path $backend "scripts\import_dataset.py")
}
if (-not (Test-Path -LiteralPath (Join-Path $frontend "node_modules"))) {
    Push-Location $frontend
    try { & npm install }
    finally { Pop-Location }
}

$api = Start-Process -FilePath "python" -ArgumentList "-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", "8000" -WorkingDirectory $root -WindowStyle Hidden -PassThru
$web = Start-Process -FilePath "npm.cmd" -ArgumentList "run", "dev" -WorkingDirectory $frontend -WindowStyle Hidden -PassThru

Write-Host "Career Quest is starting:"
Write-Host "  App: http://localhost:3000"
Write-Host "  API: http://localhost:8000/docs"
Write-Host "Press Ctrl+C to stop both servers."

try {
    while (-not $api.HasExited -and -not $web.HasExited) { Start-Sleep -Seconds 1 }
}
finally {
    if (-not $api.HasExited) { Stop-Process -Id $api.Id }
    if (-not $web.HasExited) { Stop-Process -Id $web.Id }
}
