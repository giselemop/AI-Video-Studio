[CmdletBinding()]
param(
    [string]$ComfyUrl = 'http://127.0.0.1:8188',
    [string]$WorkflowPath = 'C:\install\AI\Workflows\05_wan22_ti2v_5b_api.json',
    [string]$ComfyInput = 'C:\install\AI\ComfyUI\input',
    [string]$OutputRoot = 'C:\install\AI\Data\QA\wan22_ti2v_probe_20260815',
    [int]$TimeoutSeconds = 900
)

$ErrorActionPreference = 'Stop'
$started = Get-Date
New-Item -ItemType Directory -Force -Path $ComfyInput, $OutputRoot | Out-Null
$inputName = 'wan22_ti2v_probe_identity_20260815.png'
$inputSource = 'C:\install\AI\Data\Characters\15\standard\identity_front.png'
if (-not (Test-Path -LiteralPath (Join-Path $ComfyInput $inputName))) { Copy-Item -LiteralPath $inputSource -Destination (Join-Path $ComfyInput $inputName) }
$workflow = Get-Content -LiteralPath $WorkflowPath -Raw -Encoding UTF8 | ConvertFrom-Json
$workflow.'56'.inputs.image = $inputName
$workflow.'55'.inputs.width = 512
$workflow.'55'.inputs.height = 320
$workflow.'55'.inputs.length = 49
$workflow.'3'.inputs.seed = 2026081501
$workflow.'3'.inputs.steps = 12
$workflow.'3'.inputs.cfg = 4.5
$workflow.'41'.inputs.filename_prefix = 'video_studio/wan22_ti2v_probe_20260815'

function GpuSnapshot { return (nvidia-smi --query-gpu=memory.used,memory.free,utilization.gpu --format=csv,noheader,nounits | Out-String).Trim() }
function Read-Error($errorRecord) {
    $text = $errorRecord.ErrorDetails.Message
    if ([string]::IsNullOrWhiteSpace($text) -and $errorRecord.Exception.Response) {
        try { $reader = [IO.StreamReader]::new($errorRecord.Exception.Response.GetResponseStream()); $text = $reader.ReadToEnd(); $reader.Dispose() } catch { }
    }
    if ([string]::IsNullOrWhiteSpace($text)) { $text = $errorRecord.Exception.Message }
    return $text
}

$result = [ordered]@{
    schemaVersion = '2026-08-15.wan22-ti2v-probe.v1'
    startedAt = $started.ToString('o')
    input = $inputSource
    workflow = $WorkflowPath
    gpuBefore = GpuSnapshot
    status = 'NotStarted'
    promptId = $null
    output = $null
    error = $null
}
try {
    $payload = @{ prompt = $workflow; client_id = 'wan22-ti2v-probe-20260815' } | ConvertTo-Json -Depth 100 -Compress
    $response = Invoke-RestMethod -Uri "$ComfyUrl/prompt" -Method Post -Body ([Text.Encoding]::UTF8.GetBytes($payload)) -ContentType 'application/json'
    $promptId = [string]$response.prompt_id
    $result.promptId = $promptId
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $entry = $null
    do {
        Start-Sleep -Seconds 2
        try { $history = Invoke-RestMethod -Uri "$ComfyUrl/history/$promptId"; $prop = $history.PSObject.Properties[$promptId]; if ($prop) { $entry = $prop.Value } } catch { }
    } while ($null -eq $entry -and (Get-Date) -lt $deadline)
    if ($null -eq $entry) { throw "Timed out waiting for $promptId" }
    $status = if ($entry.status -and $entry.status.status_str) { [string]$entry.status.status_str } else { 'unknown' }
    if ($status -eq 'error') { throw ($entry.status | ConvertTo-Json -Depth 30 -Compress) }
    $items = @()
    foreach ($node in $entry.outputs.PSObject.Properties) {
        foreach ($collectionName in @('images','gifs')) {
            $collection = $node.Value.PSObject.Properties[$collectionName]
            if (-not $collection) { continue }
            foreach ($item in @($collection.Value)) {
                if ($item.filename) { $items += [pscustomobject]@{ filename = [string]$item.filename; subfolder = [string]$item.subfolder; type = if ($item.type) { [string]$item.type } else { 'output' }; collection = $collectionName } }
            }
        }
    }
    if ($items.Count -eq 0) { throw "ComfyUI returned no output for $promptId" }
    $first = $items[0]
    $query = "filename=$([Uri]::EscapeDataString($first.filename))&subfolder=$([Uri]::EscapeDataString($first.subfolder))&type=$([Uri]::EscapeDataString($first.type))"
    $ext = [IO.Path]::GetExtension($first.filename); if ([string]::IsNullOrWhiteSpace($ext)) { $ext = '.webp' }
    $target = Join-Path $OutputRoot ("wan22_ti2v_probe$ext")
    Invoke-WebRequest -Uri "$ComfyUrl/view?$query" -OutFile $target -UseBasicParsing
    $result.status = 'Succeeded'
    $result.output = [ordered]@{ path = $target; bytes = (Get-Item -LiteralPath $target).Length; sourceFile = $first.filename; durationMs = [int]((Get-Date) - $started).TotalMilliseconds }
} catch {
    $result.status = 'FailedOrBlocked'
    $result.error = Read-Error $_
}
$result.gpuAfter = GpuSnapshot
$result.finishedAt = (Get-Date).ToString('o')
$result | ConvertTo-Json -Depth 30 | Set-Content -LiteralPath (Join-Path $OutputRoot 'result.json') -Encoding UTF8
$result | ConvertTo-Json -Depth 12
