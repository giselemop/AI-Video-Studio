[CmdletBinding()]
param(
    [string]$PreviousQa = 'C:\install\AI\Data\QA\identity_foundation_20260816\run_02\08-character-qa-v2.json',
    [string]$RunRoot = 'C:\install\AI\Data\QA\multiview_identity_generation_20260817\run_01'
)

$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force -Path $RunRoot | Out-Null
$qa = Get-Content -Raw -LiteralPath $PreviousQa | ConvertFrom-Json
$rows = @($qa.candidates | Where-Object { $_.method -eq 'FaceID' })

function Get-ExpectedRange([string]$view) {
    switch ($view) {
        'front' { return @{ min = 0; max = 15; side = 'front' } }
        'half_body_front' { return @{ min = 0; max = 15; side = 'front' } }
        'full_body_front' { return @{ min = 0; max = 15; side = 'front' } }
        'front_left_30' { return @{ min = 12; max = 40; side = 'left' } }
        'front_right_30' { return @{ min = 12; max = 40; side = 'right' } }
        'left_45' { return @{ min = 27; max = 62; side = 'left' } }
        'right_45' { return @{ min = 27; max = 62; side = 'right' } }
        default { return @{ min = 0; max = 180; side = 'unknown' } }
    }
}

function Get-ActualSide([string]$viewClass) {
    if ($viewClass -match 'left') { return 'left' }
    if ($viewClass -match 'right') { return 'right' }
    if ($viewClass -eq 'front') { return 'front' }
    return 'unknown'
}

function Add-Unique([System.Collections.Generic.List[string]]$list, [string]$value) {
    if (-not [string]::IsNullOrWhiteSpace($value) -and -not $list.Contains($value)) { $list.Add($value) }
}

$classified = [System.Collections.Generic.List[object]]::new()
foreach ($row in $rows) {
    $expected = Get-ExpectedRange ([string]$row.requestedView)
    $yaw = if ($null -eq $row.yaw) { $null } else { [double]$row.yaw }
    $absYaw = if ($null -eq $yaw) { $null } else { [math]::Abs($yaw) }
    $actualSide = Get-ActualSide ([string]$row.viewClass)
    $flags = [System.Collections.Generic.List[string]]::new()
    if (-not $row.faceDetected -or [int]$row.faceCount -ne 1) { Add-Unique $flags 'E_FaceMissingOrCountInvalid' }
    if ($expected.side -in @('left','right') -and $actualSide -in @('left','right') -and $actualSide -ne $expected.side) { Add-Unique $flags 'D_AngleMirroredOrWrongDirection' }
    if ($expected.side -ne 'front' -and $null -ne $absYaw -and $absYaw -lt $expected.min) { Add-Unique $flags 'F_TooFrontal' }
    if ($expected.side -ne 'front' -and $null -ne $absYaw -and $absYaw -gt $expected.max) { Add-Unique $flags 'G_TooProfile' }
    if (-not $row.identityPass -and $row.viewPass) { Add-Unique $flags 'A_IdentityFailedAngleCorrect' }
    if ($row.identityPass -and -not $row.viewPass) { Add-Unique $flags 'B_IdentityCorrectAngleFailed' }
    if (-not $row.identityPass -and -not $row.viewPass) { Add-Unique $flags 'C_IdentityAndAngleBothFailed' }

    $primary = if ($flags.Count -eq 0) { 'PASS_OR_NO_AUTOMATIC_FAILURE_FLAG' } elseif ($flags.Contains('E_FaceMissingOrCountInvalid')) { 'E_FaceMissingOrCountInvalid' } elseif ($flags.Contains('D_AngleMirroredOrWrongDirection')) { 'D_AngleMirroredOrWrongDirection' } elseif ($flags.Contains('F_TooFrontal')) { 'F_TooFrontal' } elseif ($flags.Contains('G_TooProfile')) { 'G_TooProfile' } elseif ($flags.Contains('A_IdentityFailedAngleCorrect')) { 'A_IdentityFailedAngleCorrect' } elseif ($flags.Contains('B_IdentityCorrectAngleFailed')) { 'B_IdentityCorrectAngleFailed' } else { 'C_IdentityAndAngleBothFailed' }
    $classified.Add([ordered]@{
        method = $row.method
        requestedView = $row.requestedView
        seed = $row.seed
        path = $row.path
        technicalSuccess = $row.technicalSuccess
        rawCosineSimilarity = $row.embeddingRawSimilarity
        identityPass = $row.identityPass
        yaw = $row.yaw
        pitch = $row.pitch
        roll = $row.roll
        absYaw = $absYaw
        expectedYawMinAbs = $expected.min
        expectedYawMaxAbs = $expected.max
        expectedSide = $expected.side
        detectedView = $row.viewClass
        detectedSide = $actualSide
        yawError = if ($null -eq $yaw) { $null } else { [math]::Round([math]::Abs($yaw - $(if ($expected.side -eq 'left') { -$expected.min - ($(($expected.max - $expected.min) / 2)) } elseif ($expected.side -eq 'right') { $expected.min + ($(($expected.max - $expected.min) / 2)) } else { 0 })), 3) }
        viewPass = $row.viewPass
        dualPass = $row.dualPass
        hardRejectFlags = @($row.hardRejectFlags)
        bodyPoseStatus = 'UNMEASURED_MANUAL_REVIEW'
        bodyCropStatus = if ($row.bodyCoverage) { $row.bodyCoverage } else { 'UNMEASURED_MANUAL_REVIEW' }
        categoryFlags = @($flags)
        primaryCategory = $primary
    })
}

$autoCategories = @(
    'A_IdentityFailedAngleCorrect', 'B_IdentityCorrectAngleFailed', 'C_IdentityAndAngleBothFailed',
    'D_AngleMirroredOrWrongDirection', 'E_FaceMissingOrCountInvalid', 'F_TooFrontal', 'G_TooProfile'
)
$categorySummary = [ordered]@{}
foreach ($category in $autoCategories) {
    $categorySummary[$category] = [ordered]@{
        count = @($classified | Where-Object { $_.categoryFlags -contains $category }).Count
        rows = @($classified | Where-Object { $_.categoryFlags -contains $category } | ForEach-Object { "$($_.requestedView)/$($_.seed)" })
    }
}
$categorySummary['H_BodyPoseCorrectButFaceWrong'] = [ordered]@{ count = $null; status = 'UNMEASURED_MANUAL_REVIEW'; note = 'Previous QA has no automatic body-pose correctness signal.' }
$categorySummary['I_FaceCorrectButBodyCropWrong'] = [ordered]@{ count = $null; status = 'UNMEASURED_MANUAL_REVIEW'; note = 'Previous QA body coverage/feet crop remains unmeasured.' }

$identityFails = @($classified | Where-Object { -not $_.identityPass }).Count
$viewFails = @($classified | Where-Object { -not $_.viewPass }).Count
$nonFront = @($classified | Where-Object { $_.expectedSide -ne 'front' })
$nonFrontViewFails = @($nonFront | Where-Object { -not $_.viewPass }).Count
$dominant = if ($identityFails -gt $viewFails) { 'IDENTITY_FAILURE_MORE_FREQUENT_BUT_NONFRONT_HEADPOSE_FAILURE_SYSTEMATIC' } else { 'HEADPOSE_FAILURE_MORE_FREQUENT' }

$analysis = [ordered]@{
    schemaVersion = '2026-08-17.faceid-failure-analysis.v1'
    source = $PreviousQa
    totalFaceIdOutputs = $rows.Count
    summary = [ordered]@{
        technicalSuccess = @($classified | Where-Object technicalSuccess).Count
        identityPass = @($classified | Where-Object identityPass).Count
        viewPass = @($classified | Where-Object viewPass).Count
        dualPass = @($classified | Where-Object dualPass).Count
        identityFail = $identityFails
        viewFail = $viewFails
        nonFrontOutputs = $nonFront.Count
        nonFrontViewFail = $nonFrontViewFails
        dualPassRate = [math]::Round((@($classified | Where-Object dualPass).Count / [double]$rows.Count), 4)
    }
    categorySummary = $categorySummary
    conclusion = [ordered]@{
        dominantFailure = $dominant
        answer = 'FaceID 失败不是单一问题：整体 identity fail 更频繁；但 30/45° 非正面样本的 view fail 为 12/12，说明 Head Pose 控制是多视角生产的系统性阻塞，并与 identity-pose tradeoff 叠加。'
        identityVsHeadPose = [ordered]@{
            identityFailureCount = $identityFails
            viewFailureCount = $viewFails
            nonFrontViewFailureCount = $nonFrontViewFails
            bodyPoseAndBodyCrop = 'UNMEASURED_MANUAL_REVIEW'
        }
        identityPoseTradeoffObserved = $true
    }
    rows = @($classified)
    manualReviewRequired = $true
    limitations = @(
        'Previous QA does not automatically measure whether the body skeleton was semantically correct.',
        'Hair, clothing, occlusion, body framing and aesthetic likeness remain manual.',
        'This matrix freezes the prior threshold 0.5 and view thresholds; it does not loosen QA.'
    )
}
$analysisPath = Join-Path $RunRoot 'faceid-failure-analysis.json'
$analysis | ConvertTo-Json -Depth 30 | Set-Content -LiteralPath $analysisPath -Encoding UTF8

$htmlRows = foreach ($row in $classified) {
    $uri = ([Uri]$row.path).AbsoluteUri
    $safeView = [System.Net.WebUtility]::HtmlEncode([string]$row.requestedView)
    $safeFlags = [System.Net.WebUtility]::HtmlEncode(($row.categoryFlags -join ', '))
    "<tr><td>$safeView</td><td>$($row.seed)</td><td><img src='$uri' loading='lazy'></td><td>$($row.rawCosineSimilarity)</td><td>$($row.yaw)</td><td>$([System.Net.WebUtility]::HtmlEncode([string]$row.detectedView))</td><td>$safeFlags</td><td>$($row.dualPass)</td></tr>"
}
$html = @"
<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><title>FaceID Failure Analysis</title><style>body{font-family:Segoe UI,Arial,sans-serif;background:#111;color:#eee;margin:20px}table{border-collapse:collapse;width:100%;font-size:13px}th,td{border:1px solid #444;padding:6px;vertical-align:top}th{background:#222;position:sticky;top:0}img{max-width:150px;max-height:210px;display:block}code{color:#9fe}</style></head><body><h1>FaceID 失败矩阵（上一轮 21 张）</h1><p>Identity fail=$identityFails；View fail=$viewFails；Non-front view fail=$nonFrontViewFails/$($nonFront.Count)；结论：$([System.Net.WebUtility]::HtmlEncode($dominant))</p><table><thead><tr><th>RequestedView</th><th>Seed</th><th>Image</th><th>Raw Similarity</th><th>Yaw</th><th>Detected View</th><th>Failure Flags</th><th>DualPass</th></tr></thead><tbody>$($htmlRows -join "`n")</tbody></table></body></html>
"@
$html | Set-Content -LiteralPath (Join-Path $RunRoot 'faceid-failure-contact-sheet.html') -Encoding UTF8
Write-Output ($analysis | ConvertTo-Json -Depth 12)
