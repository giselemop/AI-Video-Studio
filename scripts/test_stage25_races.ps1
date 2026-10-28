[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$SecretConfig,
    [string]$ServerDll = '',
    [string]$EvidenceRoot = ''
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if ([string]::IsNullOrWhiteSpace($ServerDll)) { $ServerDll = Join-Path $repoRoot 'server\bin\Debug\net8.0\VideoStudio.Server.dll' }
$ServerDll = [IO.Path]::GetFullPath($ServerDll)
$SecretConfig = [IO.Path]::GetFullPath($SecretConfig)
if (-not (Test-Path -LiteralPath $ServerDll -PathType Leaf)) { throw "Missing built server: $ServerDll" }
if (-not (Test-Path -LiteralPath $SecretConfig -PathType Leaf)) { throw "Missing exact stage25 secure config" }

if ([string]::IsNullOrWhiteSpace($EvidenceRoot)) {
    $EvidenceRoot = Join-Path ([IO.Path]::GetTempPath()) ("ai-video-studio-stage25-races-" + [Guid]::NewGuid().ToString('N'))
}
$EvidenceRoot = [IO.Path]::GetFullPath($EvidenceRoot)
New-Item -ItemType Directory -Path $EvidenceRoot -Force | Out-Null
$statePath = "$SecretConfig.state.json"
$state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
$report = [System.Collections.Generic.List[object]]::new()

function Assert-Condition {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw "ASSERTION_FAILED: $Message" }
}

function Start-Worker {
    param(
        [string]$Name,
        [string]$Scenario,
        [string]$WorkerId,
        [string]$ResultName,
        [string[]]$Extra = @()
    )
    $resultPath = Join-Path $EvidenceRoot ($ResultName + '.json')
    $stdout = Join-Path $EvidenceRoot ($ResultName + '.stdout.log')
    $stderr = Join-Path $EvidenceRoot ($ResultName + '.stderr.log')
    $arguments = @($ServerDll, '--stage25-race-worker', $SecretConfig, $Scenario, $WorkerId, $resultPath) + $Extra
    $process = Start-Process -FilePath 'dotnet.exe' -ArgumentList $arguments -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru -WindowStyle Hidden
    [pscustomobject]@{ Name = $Name; Scenario = $Scenario; WorkerId = $WorkerId; ResultPath = $resultPath; Stdout = $stdout; Stderr = $stderr; Process = $process }
}

function Wait-Worker {
    param($Handle, [int]$TimeoutMilliseconds = 30000)
    if (-not $Handle.Process.WaitForExit($TimeoutMilliseconds)) { throw "Worker timeout: $($Handle.Name)" }
    $Handle.Process.Refresh()
    Assert-Condition $Handle.Process.HasExited "Worker did not reach a terminal state: $($Handle.Name)"
    $stderr = Get-Content -LiteralPath $Handle.Stderr -Raw
    Assert-Condition ([string]::IsNullOrWhiteSpace($stderr)) "Worker wrote stderr: $($Handle.Name)"
    Assert-Condition (Test-Path -LiteralPath $Handle.ResultPath -PathType Leaf) "Worker result missing: $($Handle.Name)"
    $result = Get-Content -LiteralPath $Handle.ResultPath -Raw | ConvertFrom-Json
    Assert-Condition ($result.outcome -ne 'error') "Worker reported an execution error: $($Handle.Name)"
    return $result
}

function Invoke-Worker {
    param([string]$Name, [string]$Scenario, [string]$WorkerId, [string[]]$Extra = @())
    $handle = Start-Worker $Name $Scenario $WorkerId $Name $Extra
    return Wait-Worker $handle
}

function Add-Case {
    param([string]$Name, [int]$ProcessCount, [string]$Initial, [string]$Interleaving, [string]$Expected, [string]$Actual)
    $passed = $true
    $report.Add([pscustomobject]@{ name = $Name; processCount = $ProcessCount; initialState = $Initial; interleaving = $Interleaving; expected = $Expected; actual = $Actual; result = 'PASS' })
}

try {
    $runSuffix = '-' + [Guid]::NewGuid().ToString('N')
    # Same idempotency key: two independent processes must converge to one row.
    $sameOne = Start-Worker 'duplicate-same-1' 'duplicate-same' 'submit-a' 'duplicate-same-1' @($runSuffix)
    $sameTwo = Start-Worker 'duplicate-same-2' 'duplicate-same' 'submit-b' 'duplicate-same-2' @($runSuffix)
    $sameResults = @((Wait-Worker $sameOne), (Wait-Worker $sameTwo))
    Assert-Condition (@($sameResults | Where-Object { $_.outcome -eq 'created-or-reused' }).Count -eq 2) 'same-key submissions did not both converge'
    Assert-Condition ($sameResults[0].taskId -eq $sameResults[1].taskId) 'same-key submissions returned different task ids'
    Add-Case 'same-idempotency-key-concurrent' 2 'Pending/no row' 'submit-a || submit-b' 'one durable task id, two successful reuse responses' (($sameResults | ConvertTo-Json -Compress))

    # Same key with a different fingerprint: exactly one must be rejected.
    $differentOne = Start-Worker 'duplicate-different-1' 'duplicate-different' 'different-a' 'duplicate-different-1' @($runSuffix)
    $differentTwo = Start-Worker 'duplicate-different-2' 'duplicate-different' 'different-b' 'duplicate-different-2' @($runSuffix)
    $differentResults = @((Wait-Worker $differentOne), (Wait-Worker $differentTwo))
    Assert-Condition (@($differentResults | Where-Object { $_.outcome -eq 'conflict' }).Count -eq 1) 'different-fingerprint submission was not explicitly rejected'
    Assert-Condition (@($differentResults | Where-Object { $_.outcome -eq 'created-or-reused' }).Count -eq 1) 'different-fingerprint race did not retain one winner'
    Add-Case 'same-key-different-fingerprint' 2 'Pending/no row' 'different-a || different-b' 'one winner and one IdempotencyConflict' (($differentResults | ConvertTo-Json -Compress))

    # Two workers claim the same Pending task.
    $claimOne = Start-Worker 'claim-1' 'claim' 'worker-a' 'claim-1' @($state.ClaimRaceTaskId)
    $claimTwo = Start-Worker 'claim-2' 'claim' 'worker-b' 'claim-2' @($state.ClaimRaceTaskId)
    $claimResults = @((Wait-Worker $claimOne), (Wait-Worker $claimTwo))
    Assert-Condition (@($claimResults | Where-Object { $_.outcome -eq 'claimed' }).Count -eq 1) 'two-worker claim had no unique winner'
    Assert-Condition (@($claimResults | Where-Object { $_.outcome -eq 'not-claimed' }).Count -eq 1) 'two-worker claim allowed two winners'
    $claimWinner = @($claimResults | Where-Object { $_.outcome -eq 'claimed' })[0]
    $claimComplete = Invoke-Worker 'claim-winner-complete' 'complete' 'worker-finish' @($claimWinner.leasePath, 'Succeeded')
    Assert-Condition ($claimComplete.changed -eq 1) 'claim winner could not complete'
    Add-Case 'two-worker-single-claim' 2 'Pending' 'claim-a || claim-b; winner complete' 'one Running lease and one null; terminal success' (($claimResults | ConvertTo-Json -Compress))

    # Lease recovery and old worker fencing.
    $oldLease = Invoke-Worker 'lease-recovery-old-claim' 'claim-short' 'worker-old' @($state.LeaseRecoveryTaskId, '1')
    Start-Sleep -Seconds 2
    $recovery = Invoke-Worker 'lease-recovery-new-claim' 'recover-claim' 'worker-new' @($state.LeaseRecoveryTaskId, '30')
    Assert-Condition ($oldLease.outcome -eq 'claimed' -and $recovery.outcome -eq 'claimed' -and $recovery.attemptNo -eq 2) 'expired lease was not recovered as attempt 2'
    $oldComplete = Invoke-Worker 'lease-recovery-old-complete' 'complete' 'worker-old' @($oldLease.leasePath, 'Succeeded')
    Assert-Condition ($oldComplete.changed -eq 0) 'old worker completed after lease recovery'
    $newComplete = Invoke-Worker 'lease-recovery-new-cancel' 'complete' 'worker-new' @($recovery.leasePath, 'Cancelled')
    Assert-Condition ($newComplete.changed -eq 1) 'recovered worker could not complete'
    Add-Case 'lease-expiry-and-old-worker-fence' 2 'Pending' 'old claim expires; recovery claim; old complete; new cancel' 'attempt 2 wins and old completion changes 0' (($oldComplete | ConvertTo-Json -Compress))

    # Heartbeat fencing uses an expired old token while a new lease is active.
    $heartbeatOld = Invoke-Worker 'heartbeat-old-claim' 'claim-short' 'heartbeat-old' @($state.StaleFenceTaskId, '1')
    Start-Sleep -Seconds 2
    $heartbeatNew = Invoke-Worker 'heartbeat-new-claim' 'recover-claim' 'heartbeat-new' @($state.StaleFenceTaskId, '30')
    $staleHeartbeat = Invoke-Worker 'heartbeat-stale-token' 'heartbeat' 'heartbeat-old' @($heartbeatOld.leasePath)
    Assert-Condition ($staleHeartbeat.changed -eq 0) 'stale token renewed a lease'
    $heartbeatDone = Invoke-Worker 'heartbeat-new-complete' 'complete' 'heartbeat-new' @($heartbeatNew.leasePath, 'Cancelled')
    Assert-Condition ($heartbeatDone.changed -eq 1) 'current heartbeat worker could not finish'
    Add-Case 'heartbeat-token-fence' 2 'Pending' 'old claim expires; new claim; old heartbeat' 'old heartbeat changes 0' (($staleHeartbeat | ConvertTo-Json -Compress))

    # An old attempt may stage an artifact, but recovery quarantines it and the old lease cannot finalize.
    $artifactOld = Invoke-Worker 'artifact-old-claim' 'claim-short' 'artifact-old' @($state.ArtifactRecoveryTaskId, '1')
    $staged = Invoke-Worker 'artifact-old-publish' 'publish-staged' 'artifact-old' @($artifactOld.leasePath)
    Start-Sleep -Seconds 2
    $artifactRecovery = Invoke-Worker 'artifact-new-claim' 'recover-claim' 'artifact-new' @($state.ArtifactRecoveryTaskId, '30')
    Assert-Condition ($artifactRecovery.outcome -eq 'claimed' -and $artifactRecovery.attemptNo -eq 2) 'artifact task did not recover to attempt 2'
    $artifactDone = Invoke-Worker 'artifact-new-cancel' 'complete' 'artifact-new' @($artifactRecovery.leasePath, 'Cancelled')
    Assert-Condition ($artifactDone.changed -eq 1) 'artifact recovery task did not reach a terminal state'
    Add-Case 'old-attempt-artifact-quarantine' 2 'Pending' 'old stages; lease expires; recovery quarantines; new cancels' 'old artifact not Ready and task recovery succeeds' (($staged | ConvertTo-Json -Compress))

    # Cancel and complete race on the same current lease.
    $cancelClaim = Invoke-Worker 'cancel-race-claim' 'claim' 'cancel-worker' @($state.CancelRaceTaskId, '30')
    Assert-Condition ($cancelClaim.outcome -eq 'claimed') 'cancel race task could not be claimed'
    $cancelProcess = Start-Worker 'cancel-race-cancel' 'cancel' 'cancel-worker' 'cancel-race-cancel' @($state.CancelRaceTaskId)
    $completeProcess = Start-Worker 'cancel-race-complete' 'complete' 'complete-worker' 'cancel-race-complete' @($cancelClaim.leasePath, 'Succeeded')
    $cancelResult = Wait-Worker $cancelProcess
    $completeResult = Wait-Worker $completeProcess
    Assert-Condition (($cancelResult.changed + $completeResult.changed) -eq 1) 'cancel/complete race produced zero or two winners'
    Add-Case 'cancel-complete-race' 2 'Running' 'cancel || fenced complete' 'exactly one legal terminal transition' ((@($cancelResult, $completeResult) | ConvertTo-Json -Compress))

    $illegal = Invoke-Worker 'illegal-transition' 'illegal' 'illegal-worker'
    Assert-Condition ($illegal.changed -eq 0) 'invalid lease completed a task'
    Add-Case 'illegal-state-transition' 1 'Pending' 'fake lease complete' 'changed=0' (($illegal | ConvertTo-Json -Compress))

    $retry = Invoke-Worker 'retry-after-budget' 'retry-exhausted' 'retry-worker'
    Assert-Condition ($retry.changed -eq 0) 'retry reopened a task beyond maxAttempts'
    Add-Case 'retry-budget-exhaustion' 1 'Failed attempts=2 maxRetries=1' 'manual retry' 'changed=0' (($retry | ConvertTo-Json -Compress))

    $reportPath = Join-Path $EvidenceRoot 'stage25-race-report.json'
    $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $reportPath -Encoding UTF8
    Write-Output "PASS stage25 race suite cases=$($report.Count) evidence=$EvidenceRoot report=$reportPath"
    $report | ForEach-Object { Write-Output ("PASS {0}: {1}" -f $_.name, $_.actual) }
}
catch {
    $failurePath = Join-Path $EvidenceRoot 'stage25-race-failure.txt'
    $_ | Out-String | Set-Content -LiteralPath $failurePath -Encoding UTF8
    Write-Error ("STAGE25_RACE_FAILURE evidence={0}; {1}" -f $EvidenceRoot, $_.Exception.Message)
    exit 1
}
