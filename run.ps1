param([switch]$PrepareOnly, [switch]$SmokeTest)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$frontendDir = Join-Path $projectRoot 'frontend'
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
$apiProcess = $null
$webProcess = $null
function Invoke-Checked([string]$File, [string[]]$Arguments) {
    & $File @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed ($LASTEXITCODE): $File. See the error above." }
}
function Test-Endpoint([string]$Url, [string]$Expected) {
    try { $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2; return $r.StatusCode -eq 200 -and $r.Content.Contains($Expected) } catch { return $false }
}
function Assert-PortFree([int]$Port) {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
    try { $listener.Start() } catch { throw "Port $Port is occupied. Stop its process or use the existing application; this script will not stop unrelated processes." } finally { $listener.Stop() }
}
function Stop-OwnedProcess($Process) {
    if ($Process -and -not $Process.HasExited) {
        # Next.js can own worker processes. Only terminate descendants of this launch.
        $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $($Process.Id)" -ErrorAction SilentlyContinue
        foreach ($child in $children) { $owned = Get-Process -Id $child.ProcessId -ErrorAction SilentlyContinue; if ($owned) { Stop-OwnedProcess $owned } }
        Stop-Process -Id $Process.Id -ErrorAction SilentlyContinue
    }
}
Push-Location $projectRoot
try {
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw 'Python 3.11+ is required. Install Python and add it to PATH.' }
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw 'Node.js 20.9+ and npm are required. Install Node.js.' }
    Invoke-Checked 'python' @('-c', 'import sys; assert sys.version_info >= (3,11), "Python 3.11+ required"')
    Invoke-Checked 'node' @('-e', 'const [a,b]=process.versions.node.split(".").map(Number);if(a<20||(a===20&&b<9))process.exit(1)')
    if (-not (Test-Path -LiteralPath $pythonExe)) { Invoke-Checked 'python' @('-m','venv','.venv') }
    $requirements = Join-Path $projectRoot 'backend\requirements.txt'
    $stamp = Join-Path $projectRoot '.venv\requirements.sha256'
    $hash = (Get-FileHash -LiteralPath $requirements).Hash
    if (-not (Test-Path -LiteralPath $stamp) -or (Get-Content -LiteralPath $stamp -Raw).Trim() -ne $hash) {
        Invoke-Checked $pythonExe @('-m','pip','install','-r',$requirements)
        Set-Content -LiteralPath $stamp -Value $hash
    }
    $lock = Join-Path $frontendDir 'package-lock.json'
    $npmStamp = Join-Path $frontendDir 'node_modules\.cq-lock.sha256'
    $npmHash = (Get-FileHash -LiteralPath $lock).Hash
    if (-not (Test-Path -LiteralPath $npmStamp) -or (Get-Content -LiteralPath $npmStamp -Raw).Trim() -ne $npmHash) {
        Push-Location $frontendDir
        try { Invoke-Checked 'npm.cmd' @('ci','--no-audit','--no-fund') } finally { Pop-Location }
        Set-Content -LiteralPath $npmStamp -Value $npmHash
    }
    if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'backend\data\career_quest.db'))) {
        Invoke-Checked $pythonExe @('backend/scripts/import_dataset.py')
    }
    Invoke-Checked $pythonExe @('-c','from backend.app.database import database_ready; assert database_ready(), "Database invalid: restore a backup. Automatic reset is disabled."')
    if ($PrepareOnly) { Write-Host 'Dependencies and database are ready.'; return }
    if ((Test-Endpoint 'http://127.0.0.1:8000/api/v1/health' 'connected') -and (Test-Endpoint 'http://127.0.0.1:3000' 'Career Quest')) {
        Write-Host 'Career Quest is already running: http://localhost:3000'; return
    }
    Assert-PortFree 8000
    Assert-PortFree 3000
    $apiProcess = Start-Process -FilePath $pythonExe -ArgumentList '-m','uvicorn','backend.app.main:app','--host','127.0.0.1','--port','8000' -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $projectRoot 'backend\server.log') -RedirectStandardError (Join-Path $projectRoot 'backend\server-error.log')
    $webProcess = Start-Process -FilePath 'node' -ArgumentList 'node_modules/next/dist/bin/next','dev','--hostname','127.0.0.1','--port','3000' -WorkingDirectory $frontendDir -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $frontendDir 'server.log') -RedirectStandardError (Join-Path $frontendDir 'server-error.log')
    $ready = $false
    for ($attempt=0; $attempt -lt 60; $attempt++) {
        if ($apiProcess.HasExited -or $webProcess.HasExited) { throw 'A server exited. See backend/server-error.log and frontend/server-error.log.' }
        if ((Test-Endpoint 'http://127.0.0.1:8000/api/v1/health' 'connected') -and (Test-Endpoint 'http://127.0.0.1:3000' 'Career Quest')) { $ready=$true; break }
        Start-Sleep -Seconds 1
    }
    if (-not $ready) { throw 'Startup timed out. See backend/server-error.log and frontend/server-error.log.' }
    Write-Host 'Career Quest ready: http://localhost:3000 | Ctrl+C stops this launch.'
    if ($SmokeTest) { return }
    while (-not $apiProcess.HasExited -and -not $webProcess.HasExited) { Start-Sleep -Seconds 1 }
    throw 'A server stopped unexpectedly. See the server-error.log files.'
} finally {
    Stop-OwnedProcess $webProcess
    Stop-OwnedProcess $apiProcess
    Pop-Location
}
