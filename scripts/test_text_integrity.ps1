[CmdletBinding()]
param(
    [string]$BaseUrl = 'http://127.0.0.1:18080',
    [string]$Username = $env:AI_VIDEO_STUDIO_TEST_USERNAME,
    [string]$Password = $env:AI_VIDEO_STUDIO_TEST_PASSWORD
)

$ErrorActionPreference = 'Stop'
$BaseUrl = $BaseUrl.TrimEnd('/')
Add-Type -AssemblyName System.Net.Http
if ([string]::IsNullOrWhiteSpace($Username) -or [string]::IsNullOrWhiteSpace($Password)) { throw '需要通过 -Username/-Password 或 AI_VIDEO_STUDIO_TEST_USERNAME/AI_VIDEO_STUDIO_TEST_PASSWORD 提供本机管理员测试凭据。' }
$routes = @(
    '/api/projects',
    '/api/characters',
    '/api/scenes',
    '/api/scripts',
    '/api/tasks?limit=150',
    '/api/assets',
    '/api/workflows',
    '/api/models',
    '/api/presets',
    '/api/qa/episodes',
    '/api/episodes/11',
    '/api/episodes/11/shots',
    '/api/qa/episodes/11'
)

$findings = [System.Collections.Generic.List[string]]::new()
$cookieJar = [System.Net.CookieContainer]::new()
$handler = [System.Net.Http.HttpClientHandler]::new()
$handler.CookieContainer = $cookieJar
$client = [System.Net.Http.HttpClient]::new($handler)
$client.Timeout = [TimeSpan]::FromSeconds(30)

function Invoke-Api {
    param([string]$Method, [string]$Path, [object]$Body = $null, [bool]$UseCsrf = $false)
    $request = [System.Net.Http.HttpRequestMessage]::new([System.Net.Http.HttpMethod]::new($Method), "$BaseUrl$Path")
    try {
        if ($UseCsrf -and $script:csrfToken) { [void]$request.Headers.TryAddWithoutValidation('X-CSRF-Token', $script:csrfToken) }
        if ($null -ne $Body) { $request.Content = [System.Net.Http.StringContent]::new(($Body | ConvertTo-Json -Depth 16 -Compress), [System.Text.Encoding]::UTF8, 'application/json') }
        $response = $client.SendAsync($request).GetAwaiter().GetResult()
        $raw = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        $parsed = if ([string]::IsNullOrWhiteSpace($raw)) { $null } else { $raw | ConvertFrom-Json }
        return [pscustomobject]@{ StatusCode = [int]$response.StatusCode; Body = $parsed }
    } finally { $request.Dispose() }
}

function Find-QuestionMarkRuns {
    param(
        [object]$Value,
        [string]$Path
    )

    if ($null -eq $Value) { return }
    if ($Value -is [string]) {
        if ($Value -match '\?{2,}') { $findings.Add("$Path = $Value") }
        return
    }
    if ($Value -is [System.Collections.IDictionary]) {
        foreach ($key in $Value.Keys) { Find-QuestionMarkRuns -Value $Value[$key] -Path "$Path.$key" }
        return
    }
    if ($Value -is [System.Collections.IEnumerable] -and -not ($Value -is [pscustomobject])) {
        $index = 0
        foreach ($item in $Value) {
            Find-QuestionMarkRuns -Value $item -Path "$Path[$index]"
            $index++
        }
        return
    }
    if ($Value -is [pscustomobject]) {
        foreach ($property in $Value.PSObject.Properties) {
            Find-QuestionMarkRuns -Value $property.Value -Path "$Path.$($property.Name)"
        }
    }
}

try {
    $login = Invoke-Api 'POST' '/api/auth/login' @{ username = $Username; password = $Password }
    if ($login.StatusCode -ne 200 -or -not $login.Body.csrfToken) { throw "本机管理员登录失败：HTTP $($login.StatusCode)。" }
    $script:csrfToken = $login.Body.csrfToken

foreach ($route in $routes) {
    $response = Invoke-Api 'GET' $route
    if ($response.StatusCode -ne 200) { throw "GET $route failed with HTTP $($response.StatusCode): $($response.Body.error)" }
    $payload = $response.Body
    Find-QuestionMarkRuns -Value $payload -Path $route
}

$guardPassed = $false
$invalidResponse = Invoke-Api 'POST' '/api/characters' @{ name = '编码校验??'; ageSetting = '32岁' } $true
if ($invalidResponse.StatusCode -eq 400) { $guardPassed = $true }

if (-not $guardPassed) {
    throw '连续问号的角色输入没有被后端拒绝。'
}

if ($findings.Count -gt 0) {
    $findings | ForEach-Object { Write-Error $_ }
    throw "检测到 $($findings.Count) 处连续问号乱码。"
}

Write-Host "文本完整性回归通过：$($routes.Count) 个接口无连续问号，后端拒绝疑似乱码输入。" -ForegroundColor Green
}
finally {
    try { if ($script:csrfToken) { Invoke-Api 'POST' '/api/auth/logout' $null $true | Out-Null } } catch { }
    $client.Dispose()
    $handler.Dispose()
}
