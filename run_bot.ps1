$ErrorActionPreference = "Continue"
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$logDir = Join-Path $scriptPath "logs"
$logFile = Join-Path $logDir "bot_runner.log"

if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

# Use system Python (deps already installed there)
$pythonExe = "C:\Python313\python.exe"
if (-not (Test-Path $pythonExe)) {
    $pythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source
}
if (-not $pythonExe) {
    Write-Output "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] [RUNNER] ERROR: Python not found" >> $logFile
    exit 1
}

$maxRestarts = 9999
$retryDelay = 15
$restartCount = 0

Write-Output "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] [RUNNER] Started. Python: $pythonExe" >> $logFile

while ($restartCount -lt $maxRestarts) {
    $restartCount++
    Write-Output "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] [RUNNER] Starting bot (restart #$restartCount)..." >> $logFile

    try {
        & $pythonExe "$scriptPath\main.py"
        $exitCode = $LASTEXITCODE
        Write-Output "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] [RUNNER] Bot exited (code: $exitCode). Restarting in ${retryDelay}s..." >> $logFile
    } catch {
        Write-Output "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] [RUNNER] Bot crashed: $_" >> $logFile
    }

    Start-Sleep -Seconds $retryDelay
}
