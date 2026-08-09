param(
    [string]$BaseUrl = 'http://127.0.0.1:18080',
    [switch]$RunRealGeneration,
    [int]$TimeoutMinutes = 30
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$ReportPath = Join-Path $Root 'logs\production_pipeline_test.json'
$results = [ordered]@{ startedAt = (Get-Date).ToString('o'); baseUrl = $BaseUrl; checks = @(); realGenerationRequested = $RunRealGeneration.IsPresent }

function Add-Check([string]$Name, [bool]$Passed, [string]$Message) {
    $script:results.checks += [ordered]@{ name = $Name; passed = $Passed; message = $Message }
}

function Call-Api([string]$Path, [string]$Method = 'GET', $Body = $null) {
    $params = @{ Uri = "$BaseUrl$Path"; Method = $Method; UseBasicParsing = $true }
    if ($null -ne $Body) { $params.ContentType = 'application/json'; $params.Body = ($Body | ConvertTo-Json -Depth 12) }
    # Invoke-RestMethod returns a JSON array as one object when it is returned
    # directly from a function. Enumerate it so project/episode filtering works
    # the same way as it does against a normal PowerShell pipeline.
    $response = Invoke-RestMethod @params
    if ($response -is [System.Array]) {
        foreach ($item in $response) { Write-Output $item }
    } else {
        Write-Output $response
    }
}

try {
    $health = Call-Api '/api/health'
    Add-Check 'health' $true ("database={0}; comfy={1}; ffmpeg={2}" -f $health.database.online, $health.comfy.online, $health.ffmpeg.available)
    foreach ($path in @('server\publish\VideoStudio.Server.exe', 'web\dist\index.html', 'database\migrations\002_production_pipeline.sql')) {
        $exists = Test-Path -LiteralPath (Join-Path $Root $path)
        Add-Check "file:$path" $exists ($(if ($exists) { 'present' } else { 'missing' }))
    }
    if (-not $health.database.online) {
        $results.blocker = 'MySQL credentials are not configured. Fill C:\install\AI\VideoStudio\config\local.env and rerun this script.'
        Add-Check 'database-workflow' $false $results.blocker
    } else {
        $project = (Call-Api '/api/projects' | Where-Object name -eq 'Production Pipeline Test' | Select-Object -First 1)
        if (-not $project) {
            $created = Call-Api '/api/projects' 'POST' @{ name = 'Production Pipeline Test'; description = 'Script to Episode acceptance project'; status = 'Active' }
            $project = Call-Api '/api/projects' | Where-Object id -eq $created.id | Select-Object -First 1
        }
        $episodes = @(Call-Api "/api/projects/$($project.id)/episodes")
        $episode = $episodes | Select-Object -First 1
        if (-not $episode) {
            $createdEpisode = Call-Api '/api/episodes' 'POST' @{ projectId = $project.id; episodeNumber = 1; name = 'Pipeline Test Episode'; description = 'At least five shots'; targetSeconds = 25; outputFps = 30; outputWidth = 1920; outputHeight = 1080 }
            $episode = (Call-Api "/api/episodes/$($createdEpisode.id)").episode
        }
        $scriptBody = @{ projectId = $project.id; episodeId = $episode.id; title = 'Pipeline Test Script'; language = 'en-US'; content = @"
Scene 1: train cockpit, night, storm, close-up, dolly in, 5 seconds.
Alice: The train is still running.
Bob grips the control bar and turns toward the window.

Scene 2: train carriage, night, medium shot, tracking camera, 5 seconds.
Bob: The tunnel is two minutes ahead.
Alice walks to the console and checks the red alarm.

Scene 3: outside the train, wasteland, wide shot, dolly out, 5 seconds.
Narrator: The last train crosses the storm-covered city.

Scene 4: train cockpit, interior, close-up, orbit camera, 5 seconds.
Alice looks at Bob and stays calm.

Scene 5: train carriage, interior, medium shot, static camera, 5 seconds.
Bob waves to Alice and they look forward together.
"@ }
        $script = Call-Api '/api/scripts' 'POST' $scriptBody
        $analysis = Call-Api "/api/scripts/$($script.id)/analyze" 'POST' @{ scriptId = $script.id; episodeId = $episode.id; useLlm = $true; replaceDraftShots = $true }
        Add-Check 'script-analysis' ($analysis.shots.Count -ge 5) ("provider={0}; shots={1}" -f $analysis.provider, $analysis.shots.Count)
        if ($RunRealGeneration) {
            $run = Call-Api '/api/production/start' 'POST' @{ episodeId = $episode.id; mode = 'AutoProduction'; candidateCount = 1 }
            $deadline = (Get-Date).AddMinutes($TimeoutMinutes)
            do {
                Start-Sleep -Seconds 10
                $tasks = @(Call-Api '/api/tasks?limit=200' | Where-Object episodeId -eq $episode.id)
                $videoCount = @($tasks | Where-Object { $_.taskType -match 'ImageToVideo|Video' -and $_.status -eq 'Succeeded' }).Count
            } while ($videoCount -lt 2 -and (Get-Date) -lt $deadline)
            Add-Check 'real-video-generation' ($videoCount -ge 2) ("succeededVideos={0}" -f $videoCount)
        } else {
            Add-Check 'real-video-generation' $true 'Skipped. Pass -RunRealGeneration to occupy the GPU and run real videos.'
        }
    }
} catch {
    Add-Check 'runner' $false $_.Exception.Message
    $results.error = $_.Exception.Message
}

$results.finishedAt = (Get-Date).ToString('o')
New-Item -ItemType Directory -Force -Path (Split-Path $ReportPath) | Out-Null
$results | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $ReportPath -Encoding UTF8
$results | ConvertTo-Json -Depth 12
if ($results.checks | Where-Object { -not $_.passed }) { exit 2 }
