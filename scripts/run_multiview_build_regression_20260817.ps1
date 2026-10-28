$ErrorActionPreference = 'Continue'
$projectRoot = 'C:\install\AI\VideoStudio'
$runRoot = 'C:\install\AI\Data\QA\multiview_identity_generation_20260817\run_01'
$logRoot = Join-Path $runRoot 'logs'
New-Item -ItemType Directory -Force -Path $logRoot | Out-Null

function Invoke-Captured {
    param(
        [string]$Name,
        [string]$FilePath,
        [string[]]$ArgumentList,
        [string]$WorkingDirectory = $projectRoot
    )
    $logPath = Join-Path $logRoot ($Name + '.log')
    Push-Location $WorkingDirectory
    try {
        & $FilePath @ArgumentList *> $logPath
        $exitCode = $LASTEXITCODE
    } catch {
        $_ | Out-File -FilePath $logPath -Encoding utf8
        $exitCode = 1
    } finally {
        Pop-Location
    }
    [pscustomobject]@{
        name = $Name
        command = ($FilePath + ' ' + ($ArgumentList -join ' '))
        exitCode = $exitCode
        status = if ($exitCode -eq 0) { 'PASS' } else { 'FAIL' }
        log = $logPath
        logBytes = if (Test-Path -LiteralPath $logPath) { (Get-Item -LiteralPath $logPath).Length } else { 0 }
    }
}

$results = @()
$results += Invoke-Captured -Name 'build-server' -FilePath 'dotnet' -ArgumentList @('build', 'server\VideoStudio.Server.csproj', '--nologo')
$results += Invoke-Captured -Name 'build-quality-harness' -FilePath 'dotnet' -ArgumentList @('build', 'tests\VideoStudio.QualityHarness\VideoStudio.QualityHarness.csproj', '--nologo')
$results += Invoke-Captured -Name 'quality-harness-self-test' -FilePath 'dotnet' -ArgumentList @('run', '--project', 'tests\VideoStudio.QualityHarness\VideoStudio.QualityHarness.csproj', '--no-build', '--', '--self-test')

$python = 'C:\install\AI\IdentityWorker\venv\Scripts\python.exe'
$pythonFiles = @(
    'tools\head_pose_templates\create_head_pose_templates.py',
    'tools\multiview_generation\analyze_faceid_failure_20260817.ps1'
)
$pyScripts = Get-ChildItem -LiteralPath (Join-Path $projectRoot 'tools\multiview_generation') -Filter '*.py' -File | Sort-Object FullName
$pyCompileArgs = @('-m', 'py_compile') + @($pyScripts.FullName)
$results += Invoke-Captured -Name 'python-compile-multiview-tools' -FilePath $python -ArgumentList $pyCompileArgs

$results += Invoke-Captured -Name 'git-diff-check' -FilePath 'git' -ArgumentList @('diff', '--check')

$head = (& git -C $projectRoot rev-parse HEAD 2>$null).Trim()
$dirtyCount = @(& git -C $projectRoot status --short 2>$null).Count
$failed = @($results | Where-Object { $_.exitCode -ne 0 })
$report = [ordered]@{
    generatedAt = (Get-Date).ToUniversalTime().ToString('o')
    projectRoot = $projectRoot
    gitHead = $head
    dirtyCount = $dirtyCount
    status = if ($failed.Count -eq 0) { 'PASS' } else { 'FAIL' }
    results = $results
    scope = 'Static multiview identity generation regression only; no video/TTS/action benchmark.'
}
$report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $runRoot '16-build-regression.json') -Encoding utf8
$report | ConvertTo-Json -Depth 8
