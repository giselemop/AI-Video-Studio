[CmdletBinding()]
param(
    [string]$ComfyUrl = 'http://127.0.0.1:8188',
    [string]$WorkflowPath = 'C:\install\AI\Workflows\13_sd15_ipadapter_face_v1_api.json',
    [string]$MasterPath = 'C:\install\AI\Data\Characters\15\standard\identity_front.png',
    [string]$ComfyInput = 'C:\install\AI\ComfyUI\input',
    [string]$OutputRoot = 'C:\install\AI\Data\QA\identity_pipeline_20260816',
    [int]$Steps = 22,
    [int]$TimeoutSeconds = 900
)

$ErrorActionPreference = 'Stop'
$startedAt = Get-Date
New-Item -ItemType Directory -Force -Path $ComfyInput, $OutputRoot | Out-Null

function Read-Vram {
    try {
        $stats = Invoke-RestMethod -Uri "$ComfyUrl/system_stats" -TimeoutSec 10
        $device = @($stats.devices | Select-Object -First 1)[0]
        if ($device) { return [ordered]@{ totalMiB = [math]::Round([double]$device.vram_total / 1MB, 0); freeMiB = [math]::Round([double]$device.vram_free / 1MB, 0) } }
    } catch { }
    return $null
}

function Copy-Input([string]$source, [string]$name) {
    if (-not (Test-Path -LiteralPath $source)) { throw "Missing input: $source" }
    $target = Join-Path $ComfyInput $name
    if (-not (Test-Path -LiteralPath $target)) { Copy-Item -LiteralPath $source -Destination $target }
    return $name
}

function Clone-Workflow($workflow) { return ($workflow | ConvertTo-Json -Depth 100 -Compress | ConvertFrom-Json) }

function Submit-Candidate($workflow, [string]$candidateId, [string]$category, [int64]$seed, [string]$prompt, [string]$targetPath) {
    $runStarted = Get-Date
    $beforeVram = Read-Vram
    try {
        $payload = @{ prompt = $workflow; client_id = "identity-pipeline-20260816-$candidateId-$seed" } | ConvertTo-Json -Depth 100 -Compress
        $response = Invoke-RestMethod -Uri "$ComfyUrl/prompt" -Method Post -Body ([Text.Encoding]::UTF8.GetBytes($payload)) -ContentType 'application/json'
        $promptId = [string]$response.prompt_id
        if ([string]::IsNullOrWhiteSpace($promptId)) { throw "ComfyUI did not return prompt_id" }
        $deadline = (Get-Date).AddSeconds($TimeoutSeconds); $entry = $null
        do {
            Start-Sleep -Seconds 2
            try { $history = Invoke-RestMethod -Uri "$ComfyUrl/history/$promptId" -TimeoutSec 10; $prop = $history.PSObject.Properties[$promptId]; if ($prop) { $entry = $prop.Value } } catch { }
        } while ($null -eq $entry -and (Get-Date) -lt $deadline)
        if ($null -eq $entry) { throw "Timed out waiting for $promptId" }
        $status = if ($entry.status -and $entry.status.status_str) { [string]$entry.status.status_str } else { 'unknown' }
        if ($status -eq 'error') { throw ($entry.status | ConvertTo-Json -Depth 30 -Compress) }
        $items = @()
        foreach ($node in $entry.outputs.PSObject.Properties) {
            $images = $node.Value.PSObject.Properties['images']
            if (-not $images) { continue }
            foreach ($item in @($images.Value)) {
                if ($item -and $item.filename) { $items += $item }
            }
        }
        if ($items.Count -eq 0) { throw "ComfyUI completed without an image" }
        $item = $items[0]
        $query = "filename=$([Uri]::EscapeDataString([string]$item.filename))&subfolder=$([Uri]::EscapeDataString([string]$item.subfolder))&type=$([Uri]::EscapeDataString([string]$item.type))"
        Invoke-WebRequest -Uri "$ComfyUrl/view?$query" -OutFile $targetPath -UseBasicParsing
        if (-not (Test-Path -LiteralPath $targetPath) -or (Get-Item -LiteralPath $targetPath).Length -le 0) { throw "Downloaded image is empty" }
        return [ordered]@{
            candidateId = $candidateId; category = $category; seed = $seed; status = 'Succeeded'; promptId = $promptId
            prompt = $prompt; sourceFile = [string]$item.filename; path = $targetPath; bytes = (Get-Item -LiteralPath $targetPath).Length
            startedAt = $runStarted.ToString('o'); finishedAt = (Get-Date).ToString('o'); durationMs = [int]((Get-Date) - $runStarted).TotalMilliseconds
            vramBefore = $beforeVram; vramAfter = (Read-Vram); error = $null
        }
    } catch {
        return [ordered]@{
            candidateId = $candidateId; category = $category; seed = $seed; status = 'Failed'; promptId = $null
            prompt = $prompt; sourceFile = $null; path = $null; bytes = 0
            startedAt = $runStarted.ToString('o'); finishedAt = (Get-Date).ToString('o'); durationMs = [int]((Get-Date) - $runStarted).TotalMilliseconds
            vramBefore = $beforeVram; vramAfter = (Read-Vram); error = $_.Exception.Message
        }
    }
}

$masterInput = Copy-Input $MasterPath 'identity_master_20260816.png'
$workflowBase = Get-Content -LiteralPath $WorkflowPath -Raw -Encoding UTF8 | ConvertFrom-Json
$negative = 'different person, identity drift, changing face, changing hairstyle, changing hair color, changing clothes, face morphing, multiple people, duplicate person, extra eyes, malformed eyes, deformed mouth, extra limbs, missing limbs, cropped head, blocked face, hands over face, wrong prop, hat, glasses, jewelry, watermark, text, logo, cartoon, CGI, blurry'
$basePrompt = 'same adult East Asian man as the identity reference, preserve exact face, eye shape, eyelids, nose, lips, jawline, short black hair, trimmed mustache and goatee, same dark navy collared shirt, photorealistic live-action, neutral studio light, one person'
$categories = @(
    [pscustomobject]@{ name = 'front'; count = 6; prompt = "$basePrompt, front-facing head and shoulders portrait, centered, unobstructed face" },
    [pscustomobject]@{ name = 'front_left_30'; count = 6; prompt = "$basePrompt, true front-left 30 degree three-quarter head and shoulders view, both eyes visible, no prop" },
    [pscustomobject]@{ name = 'front_right_30'; count = 6; prompt = "$basePrompt, true front-right 30 degree three-quarter head and shoulders view, both eyes visible, no prop" },
    [pscustomobject]@{ name = 'left_45'; count = 6; prompt = "$basePrompt, true left 45 degree three-quarter portrait, nose and jawline turned left, no prop" },
    [pscustomobject]@{ name = 'right_45'; count = 6; prompt = "$basePrompt, true right 45 degree three-quarter portrait, nose and jawline turned right, no prop" },
    [pscustomobject]@{ name = 'left_profile'; count = 4; prompt = "$basePrompt, true left profile portrait, one eye visible, clean silhouette, no prop" },
    [pscustomobject]@{ name = 'right_profile'; count = 4; prompt = "$basePrompt, true right profile portrait, one eye visible, clean silhouette, no prop" },
    [pscustomobject]@{ name = 'half_body'; count = 6; prompt = "$basePrompt, medium half-body portrait to the waist, full head and shoulders visible, hands away from face, no prop" },
    [pscustomobject]@{ name = 'full_body'; count = 6; prompt = "$basePrompt, full-body standing portrait, head to shoes visible, natural proportions, no prop" }
)
$generationResults = [System.Collections.Generic.List[object]]::new()
$candidateManifest = [System.Collections.Generic.List[object]]::new()
$counter = 0
foreach ($category in $categories) {
    $categoryRoot = Join-Path $OutputRoot $category.name
    New-Item -ItemType Directory -Force -Path $categoryRoot | Out-Null
    for ($i = 1; $i -le $category.count; $i++) {
        $counter++
        $candidateId = "ID$(('{0:D3}' -f $counter))"
        $seed = [int64](1600000 + $counter)
        $workflow = Clone-Workflow $workflowBase
        $workflow.'4'.inputs.image = $masterInput
        $workflow.'2'.inputs.text = $category.prompt
        $workflow.'3'.inputs.text = $negative
        $workflow.'7'.inputs.seed = $seed
        $workflow.'7'.inputs.steps = $Steps
        $workflow.'9'.inputs.filename_prefix = "video_studio/identity_pipeline_20260816_$($category.name)_$i"
        $target = Join-Path $categoryRoot "$candidateId.png"
        $row = Submit-Candidate $workflow $candidateId $category.name $seed $category.prompt $target
        $generationResults.Add($row)
        if ($row.status -eq 'Succeeded') {
            $candidateManifest.Add([ordered]@{ path = $row.path; candidateId = $candidateId; requestedView = $category.name; sourcePrompt = $category.prompt; seed = $seed })
        }
        Write-Output ("{0}/{1} {2} {3} {4}ms" -f $counter, 50, $category.name, $row.status, $row.durationMs)
    }
}

$calibration = @(
    [ordered]@{ name = 'same-master'; path = $MasterPath; expected = 'same-person' },
    [ordered]@{ name = 'known-same-three-quarter'; path = 'C:\install\AI\Data\Characters\15\standard\identity_three_quarter.png'; expected = 'same-person-but-existing-drift-risk' },
    [ordered]@{ name = 'known-same-half-body'; path = 'C:\install\AI\Data\Characters\15\standard\front_half_body.png'; expected = 'same-person-but-clothing-drift-risk' },
    [ordered]@{ name = 'known-different-side-profile'; path = 'C:\install\AI\Data\Characters\15\ref_20260811_105155_907c0faa.png'; expected = 'different-person' }
)
$manifest = [ordered]@{
    schemaVersion = '2026-08-16.character-identity-manifest.v1'
    characterId = '15'
    masterPath = $MasterPath
    identityThreshold = .85
    embeddingModel = 'UNAVAILABLE'
    scoreRange = '0..1'
    calibrationCases = $calibration
    candidates = @($candidateManifest)
    generationSummary = [ordered]@{ requested = 50; succeeded = @($generationResults | Where-Object status -eq 'Succeeded').Count; failed = @($generationResults | Where-Object status -eq 'Failed').Count }
}
$manifestPath = Join-Path $OutputRoot 'identity-manifest.json'
$generationPath = Join-Path $OutputRoot 'generation-results.json'
$manifest | ConvertTo-Json -Depth 40 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
[ordered]@{ schemaVersion = '2026-08-16.character-identity-generation.v1'; startedAt = $startedAt.ToString('o'); finishedAt = (Get-Date).ToString('o'); master = $MasterPath; results = @($generationResults); summary = $manifest.generationSummary } | ConvertTo-Json -Depth 40 | Set-Content -LiteralPath $generationPath -Encoding UTF8
Write-Output ("MANIFEST={0}" -f $manifestPath)
Write-Output ("GENERATION={0}" -f $generationPath)
if ($manifest.generationSummary.failed -gt 0) { exit 2 }
