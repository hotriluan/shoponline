# Dot-sourced by the other scripts: read a setting from the environment, else the repo-root env file.
$script:RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path

function Get-Setting([string]$name, [string]$default = "") {
    $value = [Environment]::GetEnvironmentVariable($name)
    if (-not $value) {
        $envFile = Join-Path $script:RepoRoot ".env"
        if (Test-Path $envFile) {
            foreach ($line in Get-Content $envFile -Encoding UTF8) {
                if ($line -match "^\s*$([regex]::Escape($name))\s*=\s*(.*)$") {
                    $value = $Matches[1].Trim().Trim('"').Trim("'")
                }
            }
        }
    }
    if (-not $value) { $value = $default }
    return $value
}

function ConvertFrom-DatabaseUrl([string]$url) {
    if ($url -notmatch "^postgresql(\+\w+)?://([^:]+):([^@]*)@([^:/]+)(:(\d+))?/([^?]+)") {
        throw "Chuỗi kết nối không đúng dạng postgresql://user:password@host:port/db"
    }
    return @{
        User     = $Matches[2]
        Password = [uri]::UnescapeDataString($Matches[3])
        Host     = $Matches[4]
        Port     = if ($Matches[6]) { $Matches[6] } else { "5432" }
        Database = $Matches[7]
    }
}
