[CmdletBinding()]
param([switch]$KeepRunning)

$ErrorActionPreference = 'Stop'
$comfyRoot = 'C:\install\AI\ComfyUI'
$python = Join-Path $comfyRoot 'venv\Scripts\python.exe'
$workflowRoot = 'C:\install\AI\Workflows'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Existing ComfyUI virtual environment is missing; installation/repair is not authorized.' }
if (-not (Test-Path -LiteralPath $workflowRoot -PathType Container)) { throw 'Controlled workflow root is missing.' }
if (Get-NetTCPConnection -LocalPort 8188 -State Listen -ErrorAction SilentlyContinue) { throw 'Port 8188 is already in use.' }

$stdout = Join-Path ([IO.Path]::GetTempPath()) ('ai-video-studio-stage3b-comfy-' + [Guid]::NewGuid().ToString('N') + '.stdout.log')
$stderr = Join-Path ([IO.Path]::GetTempPath()) ('ai-video-studio-stage3b-comfy-' + [Guid]::NewGuid().ToString('N') + '.stderr.log')
$process = $null
$apiProcess = $null
$apiSession = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$apiPassword = 'T' + [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
$apiStdout = Join-Path ([IO.Path]::GetTempPath()) ('ai-video-studio-stage3b-api-for-comfy-' + [Guid]::NewGuid().ToString('N') + '.stdout.log')
$apiStderr = Join-Path ([IO.Path]::GetTempPath()) ('ai-video-studio-stage3b-api-for-comfy-' + [Guid]::NewGuid().ToString('N') + '.stderr.log')
$passed = $false
try {
    $comfyArgs = @('main.py','--listen','127.0.0.1','--port','8188','--preview-method','none','--extra-model-paths-config',(Join-Path $comfyRoot 'extra_model_paths.yaml'))
    $process = Start-Process -FilePath $python -WorkingDirectory $comfyRoot -ArgumentList $comfyArgs -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru -WindowStyle Hidden

    $systemStats = $null
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Seconds 1
        try { $systemStats = Invoke-RestMethod -Uri 'http://127.0.0.1:8188/system_stats' -TimeoutSec 3; break } catch { }
        $process.Refresh()
        if ($process.HasExited) { throw 'ComfyUI exited before loopback health became available.' }
    }
    if ($null -eq $systemStats) { throw 'ComfyUI loopback health did not become available within 60 seconds.' }
    $listeners = @(Get-NetTCPConnection -LocalPort 8188 -State Listen -ErrorAction Stop)
    if ($listeners.Count -ne 1 -or $listeners[0].LocalAddress -ne '127.0.0.1') { throw 'ComfyUI listener is not exactly 127.0.0.1:8188.' }

    $objectInfo = Invoke-RestMethod -Uri 'http://127.0.0.1:8188/object_info' -TimeoutSec 30
    $nodeNames = @($objectInfo.PSObject.Properties.Name)
    if ($nodeNames.Count -lt 100) { throw "ComfyUI node registry is unexpectedly small: $($nodeNames.Count)" }
    $promptStatus = $null
    try {
        $promptProbe = Invoke-WebRequest -UseBasicParsing -Method Post -Uri 'http://127.0.0.1:8188/prompt' -ContentType 'application/json' -Body '{"prompt":{}}' -TimeoutSec 10
        $promptStatus = [int]$promptProbe.StatusCode
    }
    catch {
        if ($null -eq $_.Exception.Response) { throw }
        $promptStatus = [int]$_.Exception.Response.StatusCode
    }
    if ($promptStatus -notin @(400, 422)) { throw "ComfyUI empty-prompt guard returned unexpected HTTP $promptStatus." }

    $serverDll = 'C:\install\AI\VideoStudio\server\bin\Debug\net8.0\VideoStudio.Server.dll'
    if (-not (Test-Path -LiteralPath $serverDll -PathType Leaf)) { throw 'Built VideoStudio server is missing.' }
    $apiStart = [Diagnostics.ProcessStartInfo]::new()
    $apiStart.FileName = 'dotnet.exe'
    $apiStart.WorkingDirectory = 'C:\install\AI\VideoStudio'
    $apiStart.Arguments = '"' + $serverDll + '"'
    $apiStart.UseShellExecute = $false
    $apiStart.CreateNoWindow = $true
    $apiStart.RedirectStandardOutput = $true
    $apiStart.RedirectStandardError = $true
    $apiStart.EnvironmentVariables['AI_VIDEO_STUDIO_PREFER_ENV'] = '1'
    $apiStart.EnvironmentVariables['AI_VIDEO_STUDIO_ADMIN_USERNAME'] = 'stage3b-comfy-readonly'
    $apiStart.EnvironmentVariables['AI_VIDEO_STUDIO_ADMIN_PASSWORD'] = $apiPassword
    $apiStart.EnvironmentVariables['AI_VIDEO_STUDIO_AUTO_APPLY_SCHEMA'] = '0'
    $apiStart.EnvironmentVariables['AI_VIDEO_STUDIO_WORKER_ENABLED'] = '0'
    $apiStart.EnvironmentVariables['AI_VIDEO_STUDIO_ALLOW_DATABASE_CREATE'] = '0'
    $apiProcess = [Diagnostics.Process]::Start($apiStart)
    $apiHealth = $null
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Milliseconds 500
        try { $apiHealth = Invoke-RestMethod -Uri 'http://127.0.0.1:18080/api/health' -TimeoutSec 3; if ($apiHealth.database.online -and $apiHealth.comfy.online) { break } } catch { }
        $apiProcess.Refresh()
        if ($apiProcess.HasExited) { throw 'API exited before ComfyUI health was visible.' }
    }
    if ($null -eq $apiHealth -or -not $apiHealth.database.online -or -not $apiHealth.comfy.online) { throw 'API did not report both MySQL and ComfyUI online.' }
    $login = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:18080/api/auth/login' -WebSession $apiSession -ContentType 'application/json' -Body (@{ username = 'stage3b-comfy-readonly'; password = $apiPassword } | ConvertTo-Json -Compress) -TimeoutSec 30
    if ([string]::IsNullOrWhiteSpace($login.csrfToken)) { throw 'Read-only preflight API login did not return CSRF token.' }
    $apiWorkflowResponse = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:18080/api/workflows' -WebSession $apiSession -TimeoutSec 30
    $apiWorkflowRoot = $apiWorkflowResponse.Content | ConvertFrom-Json
    $apiWorkflows = if ($apiWorkflowRoot -is [array] -and $apiWorkflowRoot.Count -eq 1 -and $apiWorkflowRoot[0] -is [array]) { [object[]]$apiWorkflowRoot[0] } else { [object[]]$apiWorkflowRoot }
    $apiHeaders = @{ 'X-CSRF-Token' = $login.csrfToken }
    $unknownWorkflow = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:18080/api/tasks/preflight' -WebSession $apiSession -Headers $apiHeaders -ContentType 'application/json' -Body (@{ taskType = 'Image'; workflowId = 999999999; resourceClass = 'GPU'; parameters = @{ positive = 'read-only workflow whitelist probe' } } | ConvertTo-Json -Depth 10 -Compress) -TimeoutSec 30
    if ($unknownWorkflow.passed) { throw 'Unregistered workflow ID was accepted by the service preflight.' }
    $badPath = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:18080/api/tasks/preflight' -WebSession $apiSession -Headers $apiHeaders -ContentType 'application/json' -Body (@{ taskType = 'Image'; inputImagePath = '..\config\appsettings.json'; resourceClass = 'GPU'; parameters = @{ positive = 'read-only path whitelist probe' } } | ConvertTo-Json -Depth 10 -Compress) -TimeoutSec 30
    if ($badPath.passed) { throw 'Arbitrary workflow/input path was accepted by the service preflight.' }

    $workflowFiles = @(Get-ChildItem -LiteralPath $workflowRoot -Filter '*.json' -File | Sort-Object Name)
    if ($workflowFiles.Count -lt 15) { throw "Controlled workflow JSON count fell below the expected baseline: $($workflowFiles.Count)." }
    $workflowRows = foreach ($file in $workflowFiles) {
        $json = Get-Content -LiteralPath $file.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
        $hash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        $nodes = @()
        $modelCategories = @()
        foreach ($property in $json.PSObject.Properties) {
            $node = $property.Value
            if ($null -ne $node -and $node.PSObject.Properties.Name -contains 'class_type') {
                $nodes += [string]$node.class_type
                if ($node.PSObject.Properties.Name -contains 'inputs') {
                    foreach ($input in $node.inputs.PSObject.Properties) {
                        if ([string]$input.Name -match 'checkpoint|ckpt|unet') { $modelCategories += 'checkpoint/unet' }
                        elseif ([string]$input.Name -match 'lora') { $modelCategories += 'lora' }
                        elseif ([string]$input.Name -match 'vae') { $modelCategories += 'vae' }
                        elseif ([string]$input.Name -match 'clip|text_encoder') { $modelCategories += 'text-encoder/clip' }
                        elseif ([string]$input.Name -match 'control') { $modelCategories += 'controlnet' }
                        elseif ([string]$input.Name -match 'adapter') { $modelCategories += 'adapter' }
                    }
                }
            }
        }
        $missingNodes = @($nodes | Sort-Object -Unique | Where-Object { -not ($nodeNames -contains $_) })
        $registeredRow = $apiWorkflows | Where-Object { [IO.Path]::GetFileName([string]$_.path) -eq $file.Name } | Select-Object -First 1
        [pscustomobject]@{ name = $file.Name; sha256 = $hash; nodeTypes = @($nodes | Sort-Object -Unique); modelCategories = @($modelCategories | Sort-Object -Unique); missingNodes = $missingNodes; registered = ($null -ne $registeredRow); registeredWorkflowId = if ($null -ne $registeredRow) { $registeredRow.id } else { $null } }
    }
    $target = $workflowRows | Where-Object name -eq '12_ltx_face_stable_v3_api.json'
    if ($null -eq $target) { throw '12_ltx_face_stable_v3_api.json is missing.' }
    $targetJson = Get-Content -LiteralPath (Join-Path $workflowRoot $target.name) -Raw -Encoding UTF8 | ConvertFrom-Json
    $targetText = $targetJson | ConvertTo-Json -Depth 100 -Compress
    $targetMarkers = @('320','416','73','24','72','small','IPAdapter')
    $targetIssues = @()
    if ($target.name -notmatch '^12_ltx_face_stable_v3') { $targetIssues += 'target filename is not 12_ltx_face_stable_v3' }
    foreach ($required in $targetMarkers) {
        if ($targetText -notmatch [regex]::Escape($required)) { $targetIssues += "target workflow is missing marker: $required" }
    }
    if ($target.nodeTypes -notcontains 'IPAdapter') { $targetIssues += 'target workflow has no IPAdapter node/input; it uses LTXVAddGuide instead' }
    if (-not $target.registered) { $targetIssues += 'target workflow is not accepted by the VideoStudio workflow catalog' }
    if ($workflowFiles.Count -ne 15) { $targetIssues += "workflow baseline count mismatch: expected 15, observed $($workflowFiles.Count)" }
    $missing = @($workflowRows | Where-Object { $_.missingNodes.Count -gt 0 })
    if ($missing.Count -gt 0) { throw ("Controlled workflows reference unregistered nodes: " + (($missing | ForEach-Object name) -join ', ')) }

    [pscustomobject]@{
        status = if ($targetIssues.Count -eq 0 -and $missing.Count -eq 0) { 'PASS' } else { 'BLOCKED' }
        listener = '127.0.0.1:8188'
        nodeCount = $nodeNames.Count
        expectedWorkflowCount = 15
        workflowCount = $workflowRows.Count
        registeredWorkflowCount = @($workflowRows | Where-Object registered).Count
        workflows = $workflowRows
        target = [pscustomobject]@{ name = $target.name; requiredMarkers = @('12_ltx_face_stable_v3') + $targetMarkers; missingNodes = @($target.missingNodes); issues = $targetIssues }
        promptSubmission = "PASS empty prompt rejected HTTP $promptStatus; no generation prompt submitted"
        serviceWhitelist = [pscustomobject]@{ registeredWorkflowCount = $apiWorkflows.Count; sampleProperties = @($apiWorkflows | Select-Object -First 2 | ForEach-Object { @($_.PSObject.Properties.Name) }); unknownWorkflowRejected = (-not $unknownWorkflow.passed); arbitraryPathRejected = (-not $badPath.passed) }
        systemStats = [pscustomobject]@{ system = [string]$systemStats.system; devices = @($systemStats.devices | ForEach-Object { [pscustomobject]@{ name = $_.name; type = $_.type; vramTotal = $_.vram_total; vramFree = $_.vram_free } }) }
    } | ConvertTo-Json -Depth 20
    if ($targetIssues.Count -gt 0 -or $missing.Count -gt 0) { throw ('Gate 5 blocked: ' + (($targetIssues + @($missing | ForEach-Object { "unregistered nodes in $($_.name)" })) -join '; ')) }
    $passed = $true
    if ($KeepRunning) { $process = $null }
}
finally {
    if ($null -ne $apiProcess) {
        try { $apiProcess.Refresh() } catch { }
        try { if (-not $apiProcess.HasExited) { $apiProcess.Kill(); $apiProcess.WaitForExit(10000) | Out-Null } } catch { }
    }
    if ($null -ne $process) {
        try { $process.Refresh() } catch { }
        try { if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue } } catch { }
    }
    if (-not $passed -and (Test-Path -LiteralPath $stderr)) {
        Write-Output 'ComfyUI stderr tail:'
        Get-Content -LiteralPath $stderr -Tail 40
    }
}
