$ErrorActionPreference = 'Stop'
$taskRoot = 'C:\install\AI\VideoStudio'
$evidenceRoot = 'C:\install\AI\Data\CharacterStory20261027'
$receiptPath = Join-Path $evidenceRoot 'restart-recovery.json'
if (Test-Path -LiteralPath $receiptPath) { throw 'Recovery test already has a checkpoint; inspect it instead of restarting again' }
$pilot = Get-Content -LiteralPath (Join-Path $evidenceRoot 'pilot.json') -Raw | ConvertFrom-Json
$ownedIds = @($pilot.slots.PSObject.Properties | ForEach-Object { $_.Value.Video.id } | Where-Object { $_ })
$tasks = Invoke-RestMethod 'http://127.0.0.1:18080/api/tasks?limit=500'
$active = @($tasks | Where-Object { $_.status -in @('Pending','Running') })
if (@($active | Where-Object { $_.id -notin $ownedIds }).Count) { throw 'Another task is active; preserve it and skip the restart test' }
$running = @($active | Where-Object { $_.status -eq 'Running' })
if ($running.Count -ne 1) { throw 'Test requires exactly one of our real H3 tasks running' }
$targetId = $running[0].id
$submissionPath = Join-Path $evidenceRoot "..\CharacterStoryTrace\task_$targetId\submission.json"
$submission = Get-Content -LiteralPath $submissionPath -Raw | ConvertFrom-Json
$comfyBefore = Invoke-RestMethod 'http://127.0.0.1:8188/queue'
if (@($comfyBefore.queue_running).Count -ne 1 -or $comfyBefore.queue_running[0][1] -ne $submission.promptId -or @($comfyBefore.queue_pending).Count) { throw 'Comfy queue differs from the durable business receipt' }
$listener = Get-NetTCPConnection -State Listen -LocalPort 18080 | Select-Object -First 1
$process = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
$expected = Join-Path $taskRoot 'server\publish\VideoStudio.Server.exe'
if ($process.ExecutablePath -ne $expected) { throw 'Unexpected API executable; do not stop it' }
$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$auth = Invoke-RestMethod 'http://127.0.0.1:18080/api/auth/status' -WebSession $session
$session.Headers['X-CSRF-Token'] = $auth.csrfToken
$runtime = Invoke-RestMethod 'http://127.0.0.1:18080/api/minimax/local/status'
if ($runtime.queue.paused) { throw 'Queue already paused by another operator' }
$null = Invoke-RestMethod 'http://127.0.0.1:18080/api/production/pause' -Method Post -WebSession $session
$receipt = [ordered]@{status='Running';targetTaskId=$targetId;originalPromptId=$submission.promptId;originalAttempt=$submission.attemptNo;oldPid=$process.ProcessId;executable=$expected;dllSha256=(Get-FileHash -LiteralPath (Join-Path $taskRoot 'server\publish\VideoStudio.Server.dll')).Hash.ToLowerInvariant();startedAt=(Get-Date).ToString('o');ownedTaskIds=$ownedIds;comfyPids=@((Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*ComfyUI*main.py*' }).ProcessId);comfyInterrupted=$false;businessStatusManuallyChanged=$false}
$receipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $receiptPath -Encoding UTF8
# Simulate API process loss only. Do not stop ComfyUI or alter any task row.
Stop-Process -Id $process.ProcessId -ErrorAction Stop
Get-Process -Id $process.ProcessId -ErrorAction SilentlyContinue | Wait-Process -Timeout 15 -ErrorAction SilentlyContinue
$newProcess = Start-Process -FilePath $expected -WorkingDirectory $taskRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $evidenceRoot 'server-recovery.stdout.log') -RedirectStandardError (Join-Path $evidenceRoot 'server-recovery.stderr.log')
$receipt.newPid = $newProcess.Id
$newSession = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$paused = $false
$timer = [Diagnostics.Stopwatch]::StartNew()
while ($timer.Elapsed.TotalSeconds -lt 45) {
    try {
        $newAuth = Invoke-RestMethod 'http://127.0.0.1:18080/api/auth/status' -WebSession $newSession -TimeoutSec 1
        $newSession.Headers['X-CSRF-Token'] = $newAuth.csrfToken
        $null = Invoke-RestMethod 'http://127.0.0.1:18080/api/production/pause' -Method Post -WebSession $newSession -TimeoutSec 1
        $paused = $true
        break
    } catch { Start-Sleep -Milliseconds 50 }
}
$receipt.newQueuePaused = $paused
$receipt.apiReadyAfterSeconds = $timer.Elapsed.TotalSeconds
$receipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $receiptPath -Encoding UTF8
Set-Content -LiteralPath (Join-Path $taskRoot 'logs\studio.pid') -Value $newProcess.Id -Encoding ascii
if (-not $paused) { throw 'API did not become available; preserve checkpoints for recovery' }
Write-Output "API restarted ($($process.ProcessId) -> $($newProcess.Id)); ComfyUI continues original prompt for task $targetId. Queue paused while its real five-minute lease expires; verify recovery before resuming."
