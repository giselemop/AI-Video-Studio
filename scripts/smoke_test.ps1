$ErrorActionPreference = 'Stop'
$Base = 'http://127.0.0.1:18080'
function Invoke-Api($Method, $Path, $Body) {
    $params = @{ Method = $Method; Uri = "$Base$Path"; ContentType = 'application/json' }
    if ($null -ne $Body) { $params.Body = ($Body | ConvertTo-Json -Depth 20) }
    Invoke-RestMethod @params
}
$health = Invoke-Api GET '/api/health' $null
if (-not $health.database.online) { throw 'Database is offline. Fill config\local.env and run init_database.ps1 first.' }
if (-not $health.comfy.online) { throw 'ComfyUI API is offline.' }
$project = Invoke-Api POST '/api/projects' @{ name = "Studio Smoke $(Get-Date -Format HHmmss)"; description = 'Real API smoke project'; status = 'Active' }
$character = Invoke-Api POST '/api/characters' @{ name = 'Smoke Character'; ageSetting = '30'; faceFeatures = 'stable oval face, natural skin'; hair = 'dark short hair'; clothes = 'dark jacket'; fixedPrompt = 'same person, consistent identity, realistic face'; negativePrompt = 'deformed face, flicker' }
$scene = Invoke-Api POST '/api/scenes' @{ name = 'Smoke Carriage'; description = 'derelict train interior'; fixedPrompt = 'abandoned sci-fi train carriage, cinematic light'; style = 'cinematic photorealistic' }
$episode = Invoke-Api POST '/api/episodes' @{ projectId = $project.id; episodeNumber = 1; name = 'Smoke Episode'; targetSeconds = 10; outputFps = 30; outputWidth = 1920; outputHeight = 1080 }
$keyframe = 'C:\install\AI\Projects\doomsday_train\assets\train_carriage_master.png'
$shot1 = Invoke-Api POST '/api/shots' @{ projectId = $project.id; episodeId = $episode.id; shotNumber = 1; title = 'Smoke Image'; prompt = 'cinematic realistic portrait of a person inside a derelict sci-fi train carriage'; negativePrompt = 'low quality, deformed face, extra fingers'; seed = 20260809; width = 512; height = 320; status = 'Draft' }
$shot2 = Invoke-Api POST '/api/shots' @{ projectId = $project.id; episodeId = $episode.id; shotNumber = 2; title = 'Smoke I2V 5s'; prompt = 'the person slowly turns head and looks toward the window, stable face, natural motion'; negativePrompt = 'flicker, face morphing, jitter, extra limbs'; seed = 20260810; width = 512; height = 320; frames = 121; fps = 24; durationSeconds = 5; inputImagePath = $keyframe; status = 'Draft' }
$imageTask = Invoke-Api POST '/api/tasks' @{ projectId = $project.id; episodeId = $episode.id; shotId = $shot1.id; taskType = 'Image'; maxRetries = 1; parameters = @{ positive = 'cinematic realistic portrait, detailed skin, natural eyes, studio quality'; negative = 'low quality, deformed face, extra fingers'; seed = 20260809; width = 512; height = 320; steps = 20; cfg = 6.5 } }
$videoTask = Invoke-Api POST '/api/tasks' @{ projectId = $project.id; episodeId = $episode.id; shotId = $shot2.id; taskType = 'ImageToVideo'; maxRetries = 1; inputImagePath = $keyframe; parameters = @{ positive = 'the person slowly turns head and looks toward the window, stable face, natural motion'; negative = 'flicker, face morphing, jitter, extra limbs'; seed = 20260810; width = 512; height = 320; frames = 121; fps = 24; duration = 5; cfg = 3 } }
Write-Host "project=$($project.id) character=$($character.id) scene=$($scene.id) episode=$($episode.id) imageTask=$($imageTask.id) videoTask=$($videoTask.id)" -ForegroundColor Green
Write-Host 'Waiting for two real ComfyUI tasks (this can take several minutes)...'
$deadline = (Get-Date).AddMinutes(20)
do {
    Start-Sleep -Seconds 5
    $image = Invoke-Api GET "/api/tasks/$($imageTask.id)" $null
    $video = Invoke-Api GET "/api/tasks/$($videoTask.id)" $null
    Write-Host "image=$($image.task.status) video=$($video.task.status)"
    if ($image.task.status -in @('Succeeded','Failed','Cancelled') -and $video.task.status -in @('Succeeded','Failed','Cancelled')) { break }
} while ((Get-Date) -lt $deadline)
if ($image.task.status -ne 'Succeeded') { throw "Image task failed: $($image.task.errorMessage)" }
if ($video.task.status -ne 'Succeeded') { throw "Video task failed: $($video.task.errorMessage)" }
$assets = Invoke-Api GET "/api/assets?projectId=$($project.id)" $null
Write-Host ("Real smoke test passed: assets={0}" -f $assets.Count) -ForegroundColor Green
