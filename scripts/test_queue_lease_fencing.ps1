[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

$database = Get-Content -LiteralPath (Join-Path $repoRoot 'server\Database.cs') -Raw -Encoding UTF8
$leases = Get-Content -LiteralPath (Join-Path $repoRoot 'server\TaskLeaseRepository.cs') -Raw -Encoding UTF8
$queue = Get-Content -LiteralPath (Join-Path $repoRoot 'server\GenerationQueue.cs') -Raw -Encoding UTF8

Assert-True ($leases.Contains('public async Task<TaskLease?> ClaimAsync') -and $leases.Contains("status='Pending' AND paused=0") -and $leases.Contains('active_attempt_id=@attempt_id')) 'Task claiming must be conditional on Pending state and establish an attempt and lease.'
Assert-True ($leases.Contains('active_attempt_id=@attempt AND lease_token=@token AND lease_owner=@worker') -and $leases.Contains('HeartbeatAsync')) 'Lease heartbeat and terminal transitions must be fenced by attempt, token, and worker.'
Assert-True ($leases.Contains('public Task<int> SetErrorAsync') -and $leases.Contains('public Task<int> UpdateProgressAsync') -and $leases.Contains("status='Running' AND active_attempt_id=@attempt")) 'Progress and error writes must reject stale workers.'
Assert-True ($leases.Contains('DATE_ADD(NOW(3), INTERVAL @lease SECOND)') -and $leases.Contains('DATE_ADD(NOW(3), INTERVAL @deadline SECOND)')) 'Lease and deadline timestamps must be derived from database NOW(3).'
Assert-True ($leases.Contains('state_version=@version') -and $leases.Contains('AddEventAsync')) 'State transitions must advance the version and leave an audit event.'
Assert-True ($leases.Contains('public async Task<int> RetryAsync') -and $leases.Contains("status IN ('Failed','Cancelled')")) 'Retry must use the same state machine and row lock as other transitions.'
Assert-True ($queue.Contains('_leases.ClaimAsync') -and $queue.Contains('_leases.CompleteAsync') -and $queue.Contains('ProcessGpuWithGateAsync')) 'The queue must use the fenced lease gateway for claims and terminal writes.'
Assert-True ($queue.Contains('_gpuGate.AcquireAsync')) 'GPU execution must use the operating-system file gate across worker processes.'
Assert-True (-not $database.Contains('MarkTaskRunningAsync') -and -not $database.Contains('MarkTaskAsync') -and -not $database.Contains('ResetTaskForRetryAsync')) 'Legacy direct task transition methods must not remain on the repository surface.'

Write-Output 'Queue lease-fencing static regression passed: attempts, heartbeat, progress, error, retry, terminal writes, and GPU gate are worker-scoped.'
