[CmdletBinding()]
param(
    [string]$IpAddress = '192.168.31.246',
    [int]$Port = 8080,
    [string]$SiteName = 'AI Video Studio',
    [string]$AppPoolName = 'AI Video Studio',
    [string]$TrustedNetwork = ''
)

$ErrorActionPreference = 'Stop'

function Get-TrustedNetwork {
    param([string]$Address)

    $ip = Get-NetIPAddress -AddressFamily IPv4 -IPAddress $Address -ErrorAction Stop | Select-Object -First 1
    if ($null -eq $ip -or $ip.AddressState -ne 'Preferred') { throw "IPv4 address is not active: $Address" }

    $addressBytes = [System.Net.IPAddress]::Parse($Address).GetAddressBytes()
    $remainingBits = [int]$ip.PrefixLength
    $networkBytes = [byte[]]::new(4)
    for ($index = 0; $index -lt 4; $index++) {
        $mask = if ($remainingBits -ge 8) { 255 } elseif ($remainingBits -le 0) { 0 } else { [int](256 - [Math]::Pow(2, 8 - $remainingBits)) }
        $networkBytes[$index] = [byte]($addressBytes[$index] -band $mask)
        $remainingBits -= 8
    }
    $networkAddress = [System.Net.IPAddress]::new($networkBytes).ToString()
    return "$networkAddress/$($ip.PrefixLength)"
}

function Set-EnvironmentVariable {
    param(
        [System.Xml.XmlElement]$EnvironmentVariables,
        [string]$Name,
        [string]$Value
    )

    $existing = @($EnvironmentVariables.environmentVariable | Where-Object { $_.name -eq $Name }) | Select-Object -First 1
    if ($null -eq $existing) {
        $existing = $EnvironmentVariables.OwnerDocument.CreateElement('environmentVariable')
        [void]$EnvironmentVariables.AppendChild($existing)
    }
    $existing.SetAttribute('name', $Name)
    $existing.SetAttribute('value', $Value)
}

function Grant-AppPoolAccess {
    param(
        [string]$Path,
        [string]$Permission
    )

    if (-not (Test-Path -LiteralPath $Path)) { throw "Required path was not found: $Path" }
    & icacls.exe $Path /grant "IIS AppPool\$AppPoolName`:(OI)(CI)$Permission" /T /C | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Unable to grant IIS access to: $Path" }
}

if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this deployment script from an elevated Windows PowerShell session.'
}

if ($Port -lt 1 -or $Port -gt 65535) { throw 'Port must be between 1 and 65535.' }
if ([string]::IsNullOrWhiteSpace($TrustedNetwork)) { $TrustedNetwork = Get-TrustedNetwork -Address $IpAddress }

$root = Split-Path -Parent $PSScriptRoot
$publishPath = Join-Path $root 'server\publish'
$webConfigPath = Join-Path $publishPath 'web.config'
$appCmd = Join-Path $env:windir 'System32\inetsrv\appcmd.exe'
if (-not (Test-Path -LiteralPath $publishPath) -or -not (Test-Path -LiteralPath $webConfigPath)) { throw "Publish output is missing. Run scripts\publish.ps1 first: $publishPath" }
if (-not (Test-Path -LiteralPath $appCmd)) { throw 'IIS is not installed.' }
New-Item -ItemType Directory -Path (Join-Path $root 'logs') -Force | Out-Null

[xml]$webConfig = Get-Content -LiteralPath $webConfigPath -Raw
$aspNetCore = $webConfig.configuration.location.'system.webServer'.aspNetCore
if ($null -eq $aspNetCore) { throw "The publish web.config does not contain an aspNetCore handler: $webConfigPath" }
$environmentVariables = $aspNetCore.environmentVariables
if ($null -eq $environmentVariables) {
    $environmentVariables = $webConfig.CreateElement('environmentVariables')
    [void]$aspNetCore.AppendChild($environmentVariables)
}
Set-EnvironmentVariable -EnvironmentVariables $environmentVariables -Name 'AI_VIDEO_STUDIO_ALLOWED_ORIGINS' -Value "http://${IpAddress}:$Port,http://127.0.0.1:$Port,http://localhost:$Port"
Set-EnvironmentVariable -EnvironmentVariables $environmentVariables -Name 'AI_VIDEO_STUDIO_TRUSTED_NETWORKS' -Value $TrustedNetwork
$security = $webConfig.configuration.location.'system.webServer'.security
if ($null -eq $security) {
    $security = $webConfig.CreateElement('security')
    [void]$webConfig.configuration.location.'system.webServer'.AppendChild($security)
}
$requestFiltering = $security.requestFiltering
if ($null -eq $requestFiltering) {
    $requestFiltering = $webConfig.CreateElement('requestFiltering')
    [void]$security.AppendChild($requestFiltering)
}
$requestLimits = $requestFiltering.requestLimits
if ($null -eq $requestLimits) {
    $requestLimits = $webConfig.CreateElement('requestLimits')
    [void]$requestFiltering.AppendChild($requestLimits)
}
$requestLimits.SetAttribute('maxAllowedContentLength', '536870912')
$xmlWriterSettings = [System.Xml.XmlWriterSettings]::new()
$xmlWriterSettings.Encoding = [System.Text.UTF8Encoding]::new($false)
$xmlWriterSettings.Indent = $true
$xmlWriter = [System.Xml.XmlWriter]::Create($webConfigPath, $xmlWriterSettings)
try { $webConfig.Save($xmlWriter) } finally { $xmlWriter.Dispose() }

$backupName = "VideoStudio-before-$($Port)-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
& $appCmd add backup $backupName | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Unable to back up IIS configuration.' }

Import-Module WebAdministration
$poolPath = "IIS:\AppPools\$AppPoolName"
if (-not (Test-Path -LiteralPath $poolPath)) { New-WebAppPool -Name $AppPoolName | Out-Null }
Set-ItemProperty -LiteralPath $poolPath -Name managedRuntimeVersion -Value ''
Set-ItemProperty -LiteralPath $poolPath -Name processModel.identityType -Value ApplicationPoolIdentity

$site = Get-Website -Name $SiteName -ErrorAction SilentlyContinue
if ($null -ne $site) {
    $existingPath = [IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($site.PhysicalPath))
    if (-not [string]::Equals($existingPath, [IO.Path]::GetFullPath($publishPath), [StringComparison]::OrdinalIgnoreCase)) {
        throw "The existing IIS site '$SiteName' points to a different path: $existingPath"
    }
    if ($site.State -eq 'Started') { Stop-Website -Name $SiteName }
    Get-WebBinding -Name $SiteName -Protocol http | Where-Object { $_.bindingInformation -match ":${Port}:" } | ForEach-Object {
        Remove-WebBinding -Name $SiteName -Protocol http -Port $Port -IPAddress ($_.bindingInformation -split ':', 3)[0] -HostHeader ($_.bindingInformation -split ':', 3)[2]
    }
    Set-ItemProperty -LiteralPath "IIS:\Sites\$SiteName" -Name physicalPath -Value $publishPath
    Set-ItemProperty -LiteralPath "IIS:\Sites\$SiteName" -Name applicationPool -Value $AppPoolName
} else {
    New-Website -Name $SiteName -PhysicalPath $publishPath -ApplicationPool $AppPoolName -IPAddress $IpAddress -Port $Port | Out-Null
}

$siteBindings = @(Get-WebBinding -Name $SiteName -Protocol http)
if (-not ($siteBindings | Where-Object { $_.bindingInformation -eq "${IpAddress}:${Port}:" })) {
    New-WebBinding -Name $SiteName -Protocol http -IPAddress $IpAddress -Port $Port | Out-Null
}
if (-not ($siteBindings | Where-Object { $_.bindingInformation -eq "127.0.0.1:${Port}:" })) {
    New-WebBinding -Name $SiteName -Protocol http -IPAddress '127.0.0.1' -Port $Port | Out-Null
}

Grant-AppPoolAccess -Path $root -Permission 'RX'
Grant-AppPoolAccess -Path (Join-Path $root 'config') -Permission 'M'
Grant-AppPoolAccess -Path (Join-Path $root 'logs') -Permission 'M'
Grant-AppPoolAccess -Path 'C:\install\AI\Data' -Permission 'M'
Grant-AppPoolAccess -Path 'C:\install\AI\ComfyUI\input' -Permission 'M'
Grant-AppPoolAccess -Path 'C:\install\AI\ComfyUI\output' -Permission 'RX'
Grant-AppPoolAccess -Path 'C:\install\AI\Workflows' -Permission 'RX'
Grant-AppPoolAccess -Path 'C:\install\AI\Models' -Permission 'RX'
Grant-AppPoolAccess -Path 'C:\install\FFmpeg' -Permission 'RX'

$firewallRuleName = "AI Video Studio IIS $Port"
Get-NetFirewallRule -DisplayName $firewallRuleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName $firewallRuleName -Direction Inbound -Action Allow -Protocol TCP -LocalAddress $IpAddress -LocalPort $Port -RemoteAddress $TrustedNetwork -Profile Any | Out-Null

Start-Website -Name $SiteName
Write-Host "IIS deployment is running: http://${IpAddress}:$Port"
Write-Host "Initial local administrator setup: http://127.0.0.1:$Port"
Write-Host "Trusted client network: $TrustedNetwork"
