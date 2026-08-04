# Run this script as Administrator once to set up auto-start on login
# Right-click -> Run with PowerShell (Admin)

$scriptPath = "C:\Users\DELL\Desktop\Deriv\V75\R_25V1\run_bot.bat"
$taskName = "DerivTradingBot"

# Check if running as admin
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "❌ Please run as Administrator (right-click -> Run with PowerShell as Admin)" -ForegroundColor Red
    exit 1
}

# Create scheduled task
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$scriptPath`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "DELL"
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Force

Write-Host "✅ Scheduled task '$taskName' created!" -ForegroundColor Green
Write-Host "📌 The bot will start automatically on your next login." -ForegroundColor Cyan
Write-Host ""
Write-Host "To start it right now without logging out:" -ForegroundColor Yellow
Write-Host "   Start-ScheduledTask -TaskName '$taskName'" -ForegroundColor White
Write-Host ""
Write-Host "To stop it later:" -ForegroundColor Yellow
Write-Host "   Unregister-ScheduledTask -TaskName '$taskName' -Confirm:`$false" -ForegroundColor White
