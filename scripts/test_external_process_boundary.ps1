[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

function Read-Source {
    param([string]$RelativePath)
    $path = Join-Path $repoRoot $RelativePath
    Assert-True (Test-Path -LiteralPath $path -PathType Leaf) "Missing source file: $RelativePath"
    return Get-Content -LiteralPath $path -Raw -Encoding UTF8
}

$ffmpeg = Read-Source 'server/FfmpegService.cs'
$comfy = Read-Source 'server/ComfyUiClient.cs'
$queue = Read-Source 'server/GenerationQueue.cs'
$media = Read-Source 'server/MediaProductionServices.cs'
$qa = Read-Source 'server/VideoQaServices.cs'
$artifacts = Read-Source 'server/TaskArtifactService.cs'
$paths = Read-Source 'server/AssetPathPolicy.cs'

Assert-True ($ffmpeg.Contains('ArgumentList.Add') -and -not $ffmpeg.Contains('StartInfo.Arguments')) 'FFmpeg must receive arguments through ArgumentList, never a shell command string.'
Assert-True ($ffmpeg.Contains('RunToAtomicOutputAsync') -and $ffmpeg.Contains('.part-') -and $ffmpeg.Contains('File.Move(temporary, output, false)')) 'FFmpeg outputs must be written to a temporary sibling and published only after process success without replacement.'
Assert-True ($ffmpeg.Contains('process.Kill(entireProcessTree: true)')) 'FFmpeg cancellation must terminate the child process tree.'
Assert-True ($comfy.Contains('ResponseHeadersRead') -and $comfy.Contains('File.Move(temporary, target, false)') -and $comfy.Contains('using (var response') -and $comfy.Contains('await using (var outputStream = File.Create(temporary))') -and $comfy.Contains('await outputStream.FlushAsync(ct)')) 'ComfyUI downloads must close response/file handles before non-overwriting publish.'
Assert-True ($queue.Contains('CopyInputToComfyAsync') -and $queue.Contains('File.Move(temporary, target, false)')) 'ComfyUI input copies must not expose a partially written or overwritten input file.'
Assert-True ($media.Contains('SynthesizeToAsync') -and $media.Contains('GenerateToAsync') -and $media.Contains('File.Move(temporary, output, false)')) 'Task TTS and subtitle writes must publish atomically without replacement.'
Assert-True ($artifacts.Contains('CreateWorkspace') -and $artifacts.Contains('ValidateAsync') -and $artifacts.Contains('File.Move(source, finalPath, false)') -and $artifacts.Contains("'Staged'")) 'Task artifacts must be validated and finalized through a non-overwriting manifest path.'
Assert-True ($paths.Contains('await using (var read = File.OpenRead(temporaryPath))') -and $paths.Contains('File.Move(temporaryPath, finalPath, false)')) 'Upload hashing must close the read handle before atomic publication.'
Assert-True ($qa.Contains('ArgumentList.Add') -and -not $qa.Contains('StartInfo.Arguments')) 'QA frame sampling must not use shell-interpreted argument strings.'

Write-Output 'External-process boundary static regression passed: argument isolation, cancellation cleanup, and atomic media publication are present.'
