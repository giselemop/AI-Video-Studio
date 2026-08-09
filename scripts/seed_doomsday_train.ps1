$ErrorActionPreference = 'Stop'
$Base = 'http://127.0.0.1:18080'
$ProjectRoot = 'C:\install\AI\Projects\doomsday_train'
$Spec = Get-Content -Raw -Encoding UTF8 (Join-Path $ProjectRoot 'episode.json') | ConvertFrom-Json
function Invoke-Api($Method, $Path, $Body) {
    $params = @{ Method = $Method; Uri = "$Base$Path"; ContentType = 'application/json' }
    if ($null -ne $Body) { $params.Body = ($Body | ConvertTo-Json -Depth 30) }
    Invoke-RestMethod @params
}
$project = Invoke-Api POST '/api/projects' @{ name = $Spec.title; description = $Spec.description; status = 'Active' }
$characterIds = @{}
foreach ($characterPath in $Spec.characters) {
    $character = Get-Content -Raw -Encoding UTF8 $characterPath | ConvertFrom-Json
    $created = Invoke-Api POST '/api/characters' @{ projectId = $project.id; name = $character.name; ageSetting = $character.age_setting; faceFeatures = $character.face_features; hair = $character.hair; clothes = $character.clothes; bodyRatio = $character.body_ratio; fixedPrompt = $character.fixed_prompt; negativePrompt = $character.negative_prompt; anchorPath = $character.reference_images[0] }
    $characterIds[$character.name] = $created.id
}
$scene = Get-Content -Raw -Encoding UTF8 $Spec.scene | ConvertFrom-Json
$sceneCreated = Invoke-Api POST '/api/scenes' @{ projectId = $project.id; name = $scene.name; description = $scene.description; fixedPrompt = $scene.fixed_prompt; negativePrompt = $scene.negative_prompt; style = $scene.style }
$episode = Invoke-Api POST '/api/episodes' @{ projectId = $project.id; episodeNumber = [int]$Spec.episode; name = $Spec.title; description = $Spec.description; targetSeconds = [decimal]$Spec.target_seconds; outputFps = [int]$Spec.output_fps; outputWidth = [int]$Spec.output_width; outputHeight = [int]$Spec.output_height }
$keyframes = @{}
if ($Spec.scene_keyframes) { foreach ($property in $Spec.scene_keyframes.psobject.Properties) { $keyframes[$property.Name] = Join-Path $ProjectRoot $property.Value } }
if (-not $keyframes.ContainsKey('carriage')) { $keyframes['carriage'] = Join-Path $ProjectRoot 'assets\train_carriage_master.png' }
$shotIds = @()
foreach ($shot in $Spec.shots) {
    $ids = @($shot.characters | ForEach-Object { if ($characterIds.ContainsKey($_)) { $characterIds[$_] } })
    $inputPath = if ($keyframes.ContainsKey($shot.scene)) { $keyframes[$shot.scene] } else { $keyframes['carriage'] }
    $created = Invoke-Api POST '/api/shots' @{ projectId = $project.id; episodeId = $episode.id; shotNumber = [int]$shot.shot; title = "镜头 $($shot.shot): $($shot.action)"; sceneId = $sceneCreated.id; characterIds = $ids; prompt = $shot.video_prompt; negativePrompt = 'flicker, face morphing, jitter, deformed hands, extra limbs, low detail'; seed = [long]$shot.seed; width = 512; height = 320; frames = 121; fps = 24; inputImagePath = $inputPath; motionPreset = $shot.action; cameraPreset = $shot.camera; status = 'Draft' }
    $shotIds += $created.id
}
$result = [pscustomobject]@{ projectId = $project.id; episodeId = $episode.id; characterIds = $characterIds; sceneId = $sceneCreated.id; shotIds = $shotIds; createdAt = (Get-Date).ToString('o') }
$result | ConvertTo-Json -Depth 20 | Set-Content -Encoding UTF8 (Join-Path $ProjectRoot 'studio_seed_result.json')
$result | ConvertTo-Json -Depth 20
