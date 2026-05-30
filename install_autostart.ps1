# MACIE Auto-Start Installer
# Adds MACIE to Windows Task Scheduler so it starts automatically on boot
# Run this once from regular PowerShell (no Admin needed for current user tasks)

$TaskName = "MACIE-AutoStart"
$MacieRoot = "C:\SageForge\macie"
$BatchFile = "$MacieRoot\macie_autostart.bat"

# Remove existing task if present
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

# Create the action
$Action = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c `"$BatchFile`"" `
    -WorkingDirectory $MacieRoot

# Trigger: run at logon for current user
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

# Settings: run whether on battery or AC, don't stop after X minutes
$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 0) `
    -DisallowStartIfOnBatteries $false `
    -StopIfGoingOnBatteries $false `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)

# Register the task
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Starts MACIE web server and Cloudflare tunnel on login" `
    -Force

Write-Host ""
Write-Host "====================================================="
Write-Host "  MACIE Auto-Start installed successfully!"
Write-Host "====================================================="
Write-Host ""
Write-Host "  MACIE will now start automatically every time"
Write-Host "  you log into Windows."
Write-Host ""
Write-Host "  Starting MACIE now..."
Start-Process "cmd.exe" -ArgumentList "/c `"$BatchFile`"" -WindowStyle Minimized
Write-Host ""
Write-Host "  MACIE is running at:"
Write-Host "  http://localhost:5000/macie"
Write-Host "  https://core.actionforgelabs.com/macie"
Write-Host "====================================================="
