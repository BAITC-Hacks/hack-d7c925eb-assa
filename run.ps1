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

function Test-CareerEndpoint([string]$Url, [string]$Expected) {
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
        return $response.StatusCode -eq 200 -and $response.Content.Contains($Expected)
    } catch { return $false }
}

$api = $null
$web = $null
if (-not (Test-CareerEndpoint 'http://127.0.0.1:8000/api/v1/health' 'connected')) {
    $api = Start-Process -FilePath "python" -ArgumentList "-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", "8000" -WorkingDirectory $root -WindowStyle Hidden -PassThru
}
if (-not (Test-CareerEndpoint 'http://127.0.0.1:3000' 'Career Quest')) {
    $web = Start-Process -FilePath "node" -ArgumentList "node_modules/next/dist/bin/next", "dev", "--hostname", "127.0.0.1", "--port", "3000" -WorkingDirectory $frontend -WindowStyle Hidden -PassThru
}
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    if ((Test-CareerEndpoint 'http://127.0.0.1:8000/api/v1/health' 'connected') -and (Test-CareerEndpoint 'http://127.0.0.1:3000' 'Career Quest')) { break }
    if (($api -and $api.HasExited) -or ($web -and $web.HasExited)) { throw 'A server exited during startup. Check ports 3000 and 8000.' }
    Start-Sleep -Seconds 1
}
if ($attempt -eq 30) { throw 'Startup timed out. Check backend dependencies and ports 3000/8000.' }

Write-Host "Career Quest is starting:"
Write-Host "  App: http://localhost:3000"
Write-Host "  API: http://localhost:8000/docs"
Write-Host "Press Ctrl+C to stop both servers."

try {
    if (-not $api -and -not $web) { Write-Host 'Both servers are already running.'; return }
    while ((-not $api -or -not $api.HasExited) -and (-not $web -or -not $web.HasExited)) { Start-Sleep -Seconds 1 }
}
finally {
    if ($api -and -not $api.HasExited) { Stop-Process -Id $api.Id }
    if ($web -and -not $web.HasExited) { Stop-Process -Id $web.Id }
}
