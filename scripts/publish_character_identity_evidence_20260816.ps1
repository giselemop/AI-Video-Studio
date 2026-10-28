[CmdletBinding()]
param(
    [string]$QaPath = 'C:\install\AI\Data\QA\identity_pipeline_20260816\character-qa-results.json',
    [string]$OutputRoot = 'C:\install\AI\Data\QA\identity_pipeline_20260816'
)

$ErrorActionPreference = 'Stop'
$qa = Get-Content -LiteralPath $QaPath -Raw -Encoding UTF8 | ConvertFrom-Json
$packPath = Join-Path $OutputRoot 'golden-reference-pack.json'
$qa.goldenPack | ConvertTo-Json -Depth 40 | Set-Content -LiteralPath $packPath -Encoding UTF8

function Html([string]$value) {
    return [System.Net.WebUtility]::HtmlEncode([string]$value)
}
function FileUri([string]$path) {
    return ('file:///' + $path.Replace('\','/'))
}

$rows = [System.Text.StringBuilder]::new()
foreach ($item in @($qa.candidates)) {
    $hard = if (@($item.hardRejects).Count -eq 0) { 'none' } else { (@($item.hardRejects) -join ', ') }
    $img = if ($item.path) { "<img loading='lazy' src='$(Html (FileUri $item.path))' alt='$(Html $item.candidateId)' />" } else { '<div class="missing">missing</div>' }
    [void]$rows.AppendLine("<tr><td>$($img)</td><td>$(Html $item.candidateId)</td><td>$(Html $item.requestedView)</td><td>$(Html $item.detectedView)</td><td>$([math]::Round([double]$item.identityScore,3))</td><td>$([math]::Round([double]$item.overallScore,3))</td><td>$(Html $item.accepted)</td><td>$(Html $hard)</td></tr>")
}
$html = @"
<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>Character Identity Pipeline 2026-08-16</title>
<style>body{font-family:Segoe UI,Microsoft YaHei,sans-serif;margin:24px;background:#f6f7f9;color:#202124}h1{margin-bottom:4px}.summary{padding:12px;background:#fff;border:1px solid #ddd;border-radius:8px;margin:12px 0 20px}table{border-collapse:collapse;background:#fff;width:100%;font-size:13px}th,td{border:1px solid #ddd;padding:6px;vertical-align:top}th{background:#eef1f5;position:sticky;top:0}img{display:block;width:120px;height:156px;object-fit:cover}.missing{width:120px;height:156px;background:#eee;padding-top:60px;text-align:center}.bad{color:#a00}.ok{color:#176b2b}</style></head>
<body><h1>Character Identity Pipeline 2026-08-16</h1>
<div class="summary"><div><b>Character:</b> $(Html $qa.characterId)</div><div><b>Master:</b> $(Html $qa.master)</div><div><b>EmbeddingModel:</b> $(Html $qa.embeddingModel)</div><div><b>Identity threshold:</b> $($qa.identityThreshold) / score range $(Html $qa.scoreRange)</div><div><b>50 candidate generation:</b> $(@($qa.candidates).Count) QA rows, $(@($qa.candidates | Where-Object accepted).Count) auto accepted</div><div><b>Golden Pack:</b> <span class="bad">$(Html $qa.goldenPack.validation.status)</span> — $(Html $qa.goldenPack.validation.reason)</div><div><b>LoRA:</b> <span class="bad">$(Html $qa.loraStatus)</span></div><div>All rows retain first attempts; automated output requires human confirmation.</div></div>
<table><thead><tr><th>Preview</th><th>ID</th><th>RequestedView</th><th>DetectedView</th><th>Identity proxy</th><th>Overall</th><th>Accepted</th><th>Hard rejects</th></tr></thead><tbody>$rows</tbody></table>
</body></html>
"@
$htmlPath = Join-Path $OutputRoot 'character-identity-contact-sheet.html'
$html | Set-Content -LiteralPath $htmlPath -Encoding UTF8
Write-Output "PACK=$packPath"
Write-Output "CONTACT_SHEET=$htmlPath"
