# MACIE PowerShell wrapper
# ========================
#
# Drop at C:\SageForge\macie\macie.ps1 and add C:\SageForge\macie to your
# PATH. After that, from any folder:
#
#     macie "Should we use Cloudflare Access or Tunnel?"
#     macie --status
#     macie --audit 20
#     macie --shell production "Customer-safe answer please"
#     macie --json "your question" | Out-File result.json

$MacieRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$CliPath = Join-Path $MacieRoot "cli.py"

if (-not (Test-Path $CliPath)) {
    Write-Host "ERROR: cli.py not found at $CliPath" -ForegroundColor Red
    exit 2
}

python $CliPath @args
exit $LASTEXITCODE
