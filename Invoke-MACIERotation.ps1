#Requires -Version 7
<#
.SYNOPSIS
    Automated credential rotation for MACIE Production.
    Rotates OPENROUTER_API_KEY: creates a new key, deploys to Render,
    smoke-tests the live service, revokes the old key, updates .env,
    and writes an audit log entry.

.NOTES
    Run from C:\SageForge\macie or any directory — paths are absolute.
    Requires: OPENROUTER_MGMT_KEY, RENDER_API_KEY, RENDER_SERVICE_ID,
              RENDER_DEPLOY_HOOK, MACIE_ADMIN_KEY in .env.
              OPENROUTER_API_KEY and OPENROUTER_KEY_HASH are optional on
              first run; written back to .env after each successful rotation.
              OPENROUTER_KEY_HASH stores the key's id (OpenRouter's term) used
              for safe revocation on the next rotation.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$EnvPath  = 'C:\SageForge\macie\.env'
$AuditDir = 'C:\SageForge\macie\governance'
$AuditLog = "$AuditDir\audit-log.md"

# ── Logging helpers ───────────────────────────────────────────────────────────

function Write-Step    ([string]$m) { Write-Host "[$(Get-Date -f 'HH:mm:ss')] $m" -ForegroundColor Cyan }
function Write-OK      ([string]$m) { Write-Host "[$(Get-Date -f 'HH:mm:ss')] OK  $m" -ForegroundColor Green }
function Write-Warn    ([string]$m) { Write-Host "[$(Get-Date -f 'HH:mm:ss')] WARN $m" -ForegroundColor Yellow }

function Write-Audit {
    param([string]$Status, [string]$Detail)
    if (-not (Test-Path $AuditDir)) { New-Item -ItemType Directory -Path $AuditDir -Force | Out-Null }
    if (-not (Test-Path $AuditLog)) {
        Set-Content -Path $AuditLog -Value @"
# MACIE Credential Rotation — Audit Log

| Timestamp (UTC)     | Status              | Detail |
|---------------------|---------------------|--------|
"@
    }
    $ts = (Get-Date).ToUniversalTime().ToString('yyyy-MM-dd HH:mm:ss')
    Add-Content -Path $AuditLog -Value "| $ts | $Status | $Detail |"
}

function Abort {
    param([string]$Reason)
    Write-Host "[$(Get-Date -f 'HH:mm:ss')] ABORT: $Reason" -ForegroundColor Red
    Write-Audit 'ABORTED' $Reason
    exit 1
}

# ── .env loader ───────────────────────────────────────────────────────────────

function Read-EnvFile ([string]$Path) {
    $h = [ordered]@{}
    foreach ($line in (Get-Content $Path)) {
        $line = $line.Trim()
        if (-not $line -or $line.StartsWith('#')) { continue }
        $idx = $line.IndexOf('=')
        if ($idx -lt 1) { continue }
        $h[$line.Substring(0,$idx).Trim()] = $line.Substring($idx+1).Trim()
    }
    return $h
}

# Write or update a single key=value line in the .env file
function Set-EnvValue {
    param([string]$Path, [string]$Key, [string]$Value)
    $content = Get-Content $Path -Raw
    $pattern = "(?m)^$([regex]::Escape($Key))=.*$"
    if ($content -match $pattern) {
        $content = $content -replace $pattern, "$Key=$Value"
    } else {
        $content = $content.TrimEnd() + "`n$Key=$Value`n"
    }
    Set-Content -Path $Path -Value $content -NoNewline
}

# ── Step 1: Load .env ─────────────────────────────────────────────────────────

Write-Step 'Step 1 — Loading credentials from .env'
if (-not (Test-Path $EnvPath)) { Abort "Cannot find .env at $EnvPath" }

$cfg = Read-EnvFile $EnvPath

foreach ($required in @('OPENROUTER_MGMT_KEY','RENDER_API_KEY','RENDER_SERVICE_ID','RENDER_DEPLOY_HOOK','MACIE_ADMIN_KEY')) {
    if (-not $cfg.Contains($required) -or -not $cfg[$required]) {
        Abort "Required variable missing or empty in .env: $required"
    }
}

$MgmtKey      = $cfg['OPENROUTER_MGMT_KEY']
$RenderApiKey = $cfg['RENDER_API_KEY']
$ServiceId    = $cfg['RENDER_SERVICE_ID']
$DeployHook   = $cfg['RENDER_DEPLOY_HOOK']
$AdminKey     = $cfg['MACIE_ADMIN_KEY']
$OldKey       = $cfg['OPENROUTER_API_KEY']   # may be absent on first run
$OldKeyId     = $cfg['OPENROUTER_KEY_HASH']  # stores key id; may be absent on first run

if (-not $OldKey)   { Write-Warn 'OPENROUTER_API_KEY not in .env — old-key revocation will be skipped' }
if (-not $OldKeyId) { Write-Warn 'OPENROUTER_KEY_HASH not in .env — will search by name for old key id' }

# Warn if RENDER_API_KEY looks like a service ID (common misconfiguration)
if ($RenderApiKey -match '^srv-') {
    Write-Warn "RENDER_API_KEY looks like a service ID, not an API key (expected rnd_... format). Render API calls may fail."
}

Write-OK 'Credentials loaded'

# ── Step 2: Resolve production URL from Render API ────────────────────────────

Write-Step "Step 2 — Resolving MACIE production URL (service $ServiceId)"
$MACIEUrl = $null
try {
    $svc = Invoke-RestMethod `
        -Uri    "https://api.render.com/v1/services/$ServiceId" `
        -Method GET `
        -Headers @{ Authorization = "Bearer $RenderApiKey" }
    # Render v1 response shape: { id, name, serviceDetails: { url } }
    $MACIEUrl = $svc.serviceDetails.url
    if (-not $MACIEUrl) { $MACIEUrl = "https://$($svc.name).onrender.com" }
    Write-OK "Production URL: $MACIEUrl"
} catch {
    Abort "Could not resolve production URL from Render API: $($_.Exception.Message)"
}

# ── Step 3: Look up old key id by name (fallback if OPENROUTER_KEY_HASH absent) ──

if ($OldKey -and -not $OldKeyId) {
    Write-Step 'Step 3 — Searching OpenRouter key registry for old key id'
    try {
        $keyList = Invoke-RestMethod `
            -Uri    'https://openrouter.ai/api/v1/keys' `
            -Method GET `
            -Headers @{ Authorization = "Bearer $MgmtKey" }
        # Keys named MACIE-Render-YYYY-MM; pick the one whose label isn't the NEW label
        $NewLabel = "MACIE-Render-$(Get-Date -f 'yyyy-MM')"
        $match = $keyList.data | Where-Object { $_.name -like 'MACIE-Render-*' -and $_.name -ne $NewLabel } |
                 Sort-Object createdAt -Descending | Select-Object -First 1
        if ($match) {
            $OldKeyId = $match.hash
            Write-OK "Found old key: $($match.name) (id: $OldKeyId)"
        } else {
            Write-Warn 'No old MACIE-Render-* key found in registry — revocation will be skipped'
        }
    } catch {
        Write-Warn "Could not query OpenRouter key list: $($_.Exception.Message)"
    }
} else {
    Write-Step 'Step 3 — Using stored OPENROUTER_KEY_HASH (key id) for revocation'
    if ($OldKeyId) { Write-OK "Old key id: $OldKeyId" }
}

# ── Create new key (needed before approval so Pete sees the label) ────────────

$KeyLabel = "MACIE-Render-$(Get-Date -f 'yyyy-MM')"
Write-Step "Step 3b — Creating new OpenRouter key: $KeyLabel"
$newKeyResp = $null
try {
    $newKeyResp = Invoke-RestMethod `
        -Uri     'https://openrouter.ai/api/v1/keys' `
        -Method  POST `
        -Headers @{ Authorization = "Bearer $MgmtKey"; 'Content-Type' = 'application/json' } `
        -Body    (ConvertTo-Json @{ name = $KeyLabel } -Compress)
} catch {
    Abort "Failed to create new OpenRouter key: $($_.Exception.Message)"
}

$NewKey   = $newKeyResp.key
$NewKeyId = $newKeyResp.data.hash
if (-not $NewKey)   { Abort 'OpenRouter create-key response missing .key field' }
if (-not $NewKeyId) { Write-Warn 'OpenRouter create-key response missing id — revocation on next rotation will fall back to name search' }
Write-OK "New key created — id: $($NewKeyId ?? '(unavailable)')"

# ── Step 4: Approval gate ─────────────────────────────────────────────────────

Write-Host ''
Write-Host '══════════════════════════════════════════════════════' -ForegroundColor Yellow
Write-Host '  MACIE Credential Rotation — Pending Approval'        -ForegroundColor Yellow
Write-Host '══════════════════════════════════════════════════════' -ForegroundColor Yellow
Write-Host "  New key label : $KeyLabel"
Write-Host "  Render service: $ServiceId"
Write-Host "  Production URL: $MACIEUrl"
if ($OldKeyId) {
    Write-Host "  Revokes id    : $OldKeyId (old key)"
} else {
    Write-Host '  Revokes id    : (none found — skipping revocation)'
}
Write-Host '══════════════════════════════════════════════════════' -ForegroundColor Yellow
Write-Host ''
$approval = Read-Host 'New key generated. Ready to deploy to Render and revoke old key. Approve? (Y/N)'

if ($approval -notmatch '^[Yy]$') {
    Write-Step 'Aborting — cleaning up newly created key...'
    if ($NewKeyId) {
        try {
            Invoke-RestMethod `
                -Uri     "https://openrouter.ai/api/v1/keys/$NewKeyId" `
                -Method  DELETE `
                -Headers @{ Authorization = "Bearer $MgmtKey" } | Out-Null
            Write-OK 'New key revoked (no changes made to production)'
        } catch {
            Write-Warn "Could not revoke new key during cleanup: $($_.Exception.Message) — revoke manually in OpenRouter dashboard"
        }
    } else {
        Write-Warn 'No key id available for cleanup — revoke the new key manually in OpenRouter dashboard'
    }
    Write-Audit 'ABORTED' 'User declined at approval gate; new key cleaned up'
    Write-Host 'Rotation aborted. No production changes made.' -ForegroundColor Yellow
    exit 0
}

Write-Audit 'APPROVED' "Rotation approved by Pete for $KeyLabel"

# ── Step 5: Update OPENROUTER_API_KEY on Render ───────────────────────────────

Write-Step 'Step 5 — Fetching current Render environment variables'
$renderEnv = @()
try {
    $renderEnv = Invoke-RestMethod `
        -Uri    "https://api.render.com/v1/services/$ServiceId/env-vars" `
        -Method GET `
        -Headers @{ Authorization = "Bearer $RenderApiKey" }
} catch {
    Abort "Failed to fetch Render env vars: $($_.Exception.Message)"
}

# Render returns [{envVar:{key,value},...}]; rebuild as [{key,value}] for PUT
$updated = [System.Collections.Generic.List[hashtable]]::new()
$found   = $false
foreach ($item in $renderEnv) {
    $k = $item.envVar.key
    $v = if ($k -eq 'OPENROUTER_API_KEY') { $found = $true; $NewKey } else { $item.envVar.value }
    $updated.Add(@{ key = $k; value = $v })
}
if (-not $found) { $updated.Add(@{ key = 'OPENROUTER_API_KEY'; value = $NewKey }) }

Write-Step "Step 5 — Writing updated env vars to Render service $ServiceId"
try {
    Invoke-RestMethod `
        -Uri     "https://api.render.com/v1/services/$ServiceId/env-vars" `
        -Method  PUT `
        -Headers @{ Authorization = "Bearer $RenderApiKey"; 'Content-Type' = 'application/json' } `
        -Body    (ConvertTo-Json $updated -Depth 4 -Compress) | Out-Null
    Write-OK 'Render env var OPENROUTER_API_KEY updated'
} catch {
    Abort "Failed to update Render env vars: $($_.Exception.Message)"
}

# ── Step 6: Trigger redeploy ──────────────────────────────────────────────────

Write-Step 'Step 6 — Triggering Render redeploy via deploy hook'
try {
    Invoke-RestMethod -Uri $DeployHook -Method GET | Out-Null
    Write-OK 'Redeploy triggered'
} catch {
    Abort "Failed to trigger redeploy: $($_.Exception.Message)"
}
Write-Audit 'DEPLOYED' "New key pushed to Render; redeploy triggered for $ServiceId"

# ── Step 7: Poll health endpoint (max 3 minutes) ──────────────────────────────

Write-Step "Step 7 — Polling $MACIEUrl/macie/status (max 3 min, every 10 s)"
$deadline = (Get-Date).AddMinutes(3)
$healthy  = $false
while ((Get-Date) -lt $deadline) {
    try {
        $h = Invoke-RestMethod -Uri "$MACIEUrl/macie/status" -Method GET -TimeoutSec 8
        if ($h) {
            $healthy = $true
            Write-OK "Service healthy — roster: $($h.roster -join ', ')"
            break
        }
    } catch {
        Write-Host "[$(Get-Date -f 'HH:mm:ss')] ...waiting ($($_.Exception.Message))" -ForegroundColor DarkGray
    }
    Start-Sleep 10
}

if (-not $healthy) {
    Abort 'SMOKE TEST FAILED: service did not become healthy within 3 minutes. Old key preserved.'
}

# ── Step 8: Verify agent registry ─────────────────────────────────────────────

Write-Step "Step 8 — Verifying agent registry at $MACIEUrl/macie/agents"
try {
    $agents = Invoke-RestMethod `
        -Uri     "$MACIEUrl/macie/agents" `
        -Method  GET `
        -Headers @{ 'X-Admin-Key' = $AdminKey }
    $count = @($agents.agents).Count
    Write-OK "Registry healthy — $count agent(s) registered"
} catch {
    Abort "SMOKE TEST FAILED: /macie/agents returned an error. Old key preserved. Error: $($_.Exception.Message)"
}

Write-Audit 'SMOKE_PASSED' "Health OK; registry responded with $count agent(s)"

# ── Step 9: Revoke old key ────────────────────────────────────────────────────

Write-Step 'Step 9 — Revoking old OpenRouter key'
if ($OldKeyId) {
    try {
        Invoke-RestMethod `
            -Uri     "https://openrouter.ai/api/v1/keys/$OldKeyId" `
            -Method  DELETE `
            -Headers @{ Authorization = "Bearer $MgmtKey" } | Out-Null
        Write-OK "Old key revoked (id: $OldKeyId)"
        Write-Audit 'OLD_KEY_REVOKED' "Key id $OldKeyId revoked via OpenRouter management API"
    } catch {
        Write-Warn "Could not revoke old key: $($_.Exception.Message) — revoke manually at openrouter.ai/settings/keys"
    }
} else {
    Write-Warn 'Step 9 skipped — no old key id available'
}

# ── Step 10: Confirm old key is dead (expect 401) ─────────────────────────────

Write-Step 'Step 10 — Testing old key (expect 401)'
if ($OldKey) {
    try {
        $r = Invoke-WebRequest `
            -Uri     'https://openrouter.ai/api/v1/models' `
            -Method  GET `
            -Headers @{ Authorization = "Bearer $OldKey" } `
            -SkipHttpErrorCheck
        if ($r.StatusCode -eq 401) {
            Write-OK 'Old key correctly rejected with 401'
            Write-Audit 'OLD_KEY_DEAD' 'Old key returns 401 as expected'
        } else {
            Write-Warn "Old key returned HTTP $($r.StatusCode) — revocation may still be propagating"
        }
    } catch {
        Write-Warn "Could not test old key: $($_.Exception.Message)"
    }
} else {
    Write-Warn 'Step 10 skipped — OPENROUTER_API_KEY was not in .env'
}

# ── Step 11: Update local .env ────────────────────────────────────────────────

Write-Step 'Step 11 — Updating .env with new key and id'
Set-EnvValue -Path $EnvPath -Key 'OPENROUTER_API_KEY'  -Value $NewKey
Set-EnvValue -Path $EnvPath -Key 'OPENROUTER_KEY_HASH' -Value ($NewKeyId ?? '')
Write-OK '.env updated (OPENROUTER_API_KEY + OPENROUTER_KEY_HASH)'

# ── Step 12: Write audit log entry ────────────────────────────────────────────

Write-Audit 'ROTATION_COMPLETE' "Key $KeyLabel active; new id $($NewKeyId ?? 'n/a'); old id $($OldKeyId ?? 'n/a')"
Write-OK "Audit log entry written to $AuditLog"

# ── Step 13: Register Windows Task Scheduler job ──────────────────────────────

Write-Host ''
Write-Host '══════════════════════════════════════════════════════' -ForegroundColor Cyan
Write-Host '  Task Scheduler Registration'                         -ForegroundColor Cyan
Write-Host '══════════════════════════════════════════════════════' -ForegroundColor Cyan
Write-Host '  Task   : MACIE-Credential-Rotation'
Write-Host '  Runs   : Every 90 days at 09:00 AM'
Write-Host "  Script : $PSCommandPath"
Write-Host '══════════════════════════════════════════════════════' -ForegroundColor Cyan
Write-Host ''
$schedApproval = Read-Host 'Register Windows Task Scheduler job for auto-rotation every 90 days? (Y/N)'

if ($schedApproval -match '^[Yy]$') {
    $taskName = 'MACIE-Credential-Rotation'
    $action   = New-ScheduledTaskAction `
                    -Execute  'pwsh.exe' `
                    -Argument "-NonInteractive -File `"$PSCommandPath`""
    # Daily with 90-day interval = runs every 90 days
    $trigger  = New-ScheduledTaskTrigger -Daily -DaysInterval 90 -At '09:00'
    $settings = New-ScheduledTaskSettingsSet `
                    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
                    -StartWhenAvailable `
                    -RunOnlyIfNetworkAvailable
    $principal = New-ScheduledTaskPrincipal `
                    -UserId    $env:USERNAME `
                    -LogonType Interactive `
                    -RunLevel  Limited

    try {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
        Register-ScheduledTask `
            -TaskName   $taskName `
            -Action     $action `
            -Trigger    $trigger `
            -Settings   $settings `
            -Principal  $principal `
            -Description 'MACIE OpenRouter credential rotation — every 90 days' | Out-Null
        Write-OK "Task '$taskName' registered — next run at 09:00 in 90 days"
        Write-Audit 'SCHEDULER_REGISTERED' "Windows Task Scheduler job $taskName registered (90-day interval)"
    } catch {
        Write-Warn "Could not register scheduled task: $($_.Exception.Message) — register manually if needed"
    }
} else {
    Write-Host 'Skipped task scheduler registration.' -ForegroundColor Yellow
}

# ── Done ──────────────────────────────────────────────────────────────────────

Write-Host ''
Write-Host '══════════════════════════════════════════════════════' -ForegroundColor Green
Write-Host '  MACIE Credential Rotation COMPLETE'                  -ForegroundColor Green
Write-Host '══════════════════════════════════════════════════════' -ForegroundColor Green
Write-Host "  Active key  : $KeyLabel"
Write-Host "  .env        : $EnvPath"
Write-Host "  Audit log   : $AuditLog"
Write-Host '══════════════════════════════════════════════════════' -ForegroundColor Green
