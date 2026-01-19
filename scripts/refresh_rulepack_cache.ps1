param(
    [string]$CachePath = "rulepack_cache.json"
)

$ErrorActionPreference = "Stop"

Write-Host "Connecting to M365 Purview (Connect-IPPSSession -Device)..."
Connect-IPPSSession 

Write-Host "Fetching DLP Sensitive Information Type rule packs..."
$rulePacks = Get-DlpSensitiveInformationTypeRulePackage

$items = @()
foreach ($pack in $rulePacks) {
    $name = $pack.Name
    if (-not $name) { $name = $pack.RulePackName }
    if (-not $name) { $name = $pack.Identity }

    $version = $pack.Version
    if (-not $version) { $version = $pack.RulePackVersion }

    $bytes = $null
    if ($null -ne $pack.FileData) {
        $bytes = $pack.FileData
    } elseif ($null -ne $pack.RulePack) {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($pack.RulePack)
    } elseif ($null -ne $pack.Xml) {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($pack.Xml)
    }

    $base64 = $null
    if ($bytes) {
        $base64 = [Convert]::ToBase64String($bytes)
    }

    $items += [pscustomobject]@{
        name    = $name
        version = $version
        id      = $pack.Identity
        base64  = $base64
    }
}

$payload = [pscustomobject]@{
    generated_at = (Get-Date).ToString("o")
    items        = $items
}

$payload | ConvertTo-Json -Depth 5 | Set-Content -Path $CachePath -Encoding UTF8

Write-Host "Saved rule pack cache to $CachePath"
Write-Host "If any items have empty base64, update the script to match your tenant properties."
