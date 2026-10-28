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

$policy = Read-Source 'server/ScriptAndPromptServices.cs'
$audit = Read-Source 'server/LlmEgressServices.cs'
$program = Read-Source 'server/Program.cs'
$settings = Read-Source 'server/ProductionEndpoints.cs'

Assert-True ($policy.Contains('class LlmEndpointPolicy')) 'LLM endpoint policy is missing.'
Assert-True ($policy.Contains('api.openai.com') -and $policy.Contains('api.deepseek.com')) 'Only the documented public LLM hosts may be allowlisted.'
Assert-True ($policy.Contains('Dns.GetHostAddressesAsync')) 'LLM host validation must resolve and inspect DNS results.'
Assert-True ($policy.Contains('IsBlockedAddress')) 'LLM host validation must reject private, reserved, and multicast addresses.'
Assert-True ($policy.Contains('uri.Scheme != Uri.UriSchemeHttps')) 'External LLM egress must require HTTPS.'
Assert-True ($policy.Contains('AllowAutoRedirect') -eq $false) 'Redirect handling belongs to the HttpClient boundary, not the provider.'
Assert-True ($policy.Contains('ReadBoundedBodyAsync') -and $policy.Contains('2 * 1024 * 1024')) 'LLM responses must have a bounded body read.'
Assert-True ($policy.Contains('systemPrompt.Length > 128 * 1024') -and $policy.Contains('userPrompt.Length > 512 * 1024')) 'LLM prompt sizes must be bounded before sending.'
Assert-True ($policy.Contains('RecordEgressAuditAsync') -and $policy.Contains('llm.egress.allowed') -and $policy.Contains('llm.egress.rejected')) 'LLM allow/reject decisions must leave a non-secret audit record.'
Assert-True ($audit.Contains('RedactedPreview') -and $audit.Contains('redacted_preview') -and $audit.Contains('BudgetRejected') -and $audit.Contains('Timeout') -and $audit.Contains('LLM_TIMEOUT')) 'LLM audit must store redacted previews and explicit budget/timeout outcomes.'
Assert-True ($audit.Contains('MaxPromptChars') -and $audit.Contains('DailyPromptChars') -and $audit.Contains('BudgetLockName')) 'LLM prompt, token, daily budget, and cross-process budget checks must be present.'
Assert-True ($program.Contains('AllowAutoRedirect = false') -and $program.Contains('MaxResponseContentBufferSize = 2 * 1024 * 1024') -and $audit.Contains('TimeoutMs')) 'LLM redirect, response-size, and timeout bounds must be enforced at the HTTP/audit boundary.'
Assert-True ($policy.Contains('LlmRedirectBlockedException') -and $audit.Contains('redirect_count=@redirect') -and $audit.Contains('LLM_REDIRECT_BLOCKED')) 'Redirect responses must be rejected and audited with a redirect count.'
Assert-True ($program.Contains('MaxResponseContentBufferSize = 2 * 1024 * 1024') -and $program.Contains('AllowAutoRedirect = false')) 'The named LLM HttpClient must disable redirects and cap buffering.'
Assert-True ($settings.Contains('endpointPolicy.ValidateAsync') -and $settings.Contains('validation.BaseUri')) 'The settings endpoint must validate and persist only the normalized endpoint.'
Assert-True ($settings.Contains('apiKeyConfigured') -and -not $settings.Contains('apiKey = await repo.GetSettingAsync("llm.api_key"')) 'LLM settings responses must not return the API key.'

Write-Output 'LLM egress static boundary regression passed: provider allowlist, DNS checks, HTTPS, redirect, prompt, response, and secret-return guards are present.'
