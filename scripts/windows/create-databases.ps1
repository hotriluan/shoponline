<#
.SYNOPSIS
  Create the shoponline databases and the application role on the local PostgreSQL 16.

.DESCRIPTION
  dev  -> shoponline_dev and shoponline_test
  prod -> shoponline
  The script asks for the postgres superuser password and the new application password;
  neither is stored. It lists existing databases first so you can confirm the server is
  not used for something else. Safe to rerun: existing role/databases are left as is.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\windows\create-databases.ps1 -Environment dev
#>
param(
    [Parameter(Mandatory = $true)][ValidateSet("dev", "prod")][string]$Environment,
    [string]$AppRole = "shoponline_app",
    [string]$PgBin = "C:\Program Files\PostgreSQL\16\bin",
    [int]$Port = 5432,
    # Optional: write the repo-root env file (only if it does not exist yet)
    [switch]$WriteEnvFile,
    [string]$DataDir = "C:\shoponline-data"
)

$ErrorActionPreference = "Stop"
$psql = Join-Path $PgBin "psql.exe"
if (-not (Test-Path $psql)) { throw "Không thấy psql tại $psql" }

$service = Get-Service -Name "postgresql*" -ErrorAction SilentlyContinue
if (-not $service -or $service.Status -ne "Running") { throw "Dịch vụ PostgreSQL chưa chạy" }

function Read-Plain([string]$prompt) {
    $secure = Read-Host -Prompt $prompt -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
}

$env:PGPASSWORD = Read-Plain "Mật khẩu superuser postgres"
try {
    function Invoke-Sql([string]$db, [string]$sql) {
        $out = & $psql -h localhost -p $Port -U postgres -d $db -v ON_ERROR_STOP=1 -tAc $sql
        if ($LASTEXITCODE -ne 0) { throw "psql lỗi: $sql" }
        return $out
    }

    Write-Host "Database hiện có trên máy chủ:"
    Invoke-Sql "postgres" "SELECT datname FROM pg_database WHERE NOT datistemplate ORDER BY 1" |
        ForEach-Object { Write-Host "  $_" }
    $answer = Read-Host "Tiếp tục tạo database cho shoponline? (y/N)"
    if ($answer -ne "y") { Write-Host "Dừng."; exit 1 }

    $appPassword = $null
    $roleExists = Invoke-Sql "postgres" "SELECT 1 FROM pg_roles WHERE rolname = '$AppRole'"
    if (-not $roleExists) {
        $appPassword = Read-Plain "Mật khẩu mới cho role $AppRole (lưu vào kho bí mật)"
        $escaped = $appPassword.Replace("'", "''")
        Invoke-Sql "postgres" "CREATE ROLE $AppRole LOGIN PASSWORD '$escaped'" | Out-Null
        Write-Host "Đã tạo role $AppRole"
    } else {
        Write-Host "Role $AppRole đã có, giữ nguyên"
    }

    # @() keeps a one-element list a list; otherwise $databases[0] is the first character.
    $databases = @(if ($Environment -eq "dev") { "shoponline_dev", "shoponline_test" } else { "shoponline" })
    foreach ($db in $databases) {
        $exists = Invoke-Sql "postgres" "SELECT 1 FROM pg_database WHERE datname = '$db'"
        if ($exists) {
            Write-Host "Database $db đã có, giữ nguyên"
        } else {
            Invoke-Sql "postgres" "CREATE DATABASE $db OWNER $AppRole ENCODING 'UTF8' TEMPLATE template0" | Out-Null
            Write-Host "Đã tạo database $db"
        }
        Invoke-Sql $db "REVOKE ALL ON DATABASE $db FROM PUBLIC" | Out-Null
    }
    Write-Host "Xong. Chuỗi kết nối: postgresql+psycopg://${AppRole}:<mật khẩu>@localhost:$Port/<database>"

    if ($WriteEnvFile) {
        $EnvFile = Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..\..")) ".env"
        if (Test-Path $EnvFile) {
            Write-Host "$EnvFile đã có, không ghi đè"
        } else {
            if (-not $appPassword) { $appPassword = Read-Plain "Mật khẩu hiện tại của role $AppRole (để ghi vào $EnvFile)" }
            $encoded = [uri]::EscapeDataString($appPassword)
            $bytes = New-Object byte[] 48
            [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
            $secret = [Convert]::ToBase64String($bytes)
            $base = "postgresql+psycopg://${AppRole}:$encoded@localhost:$Port"
            $lines = @(
                "SHOPONLINE_DATABASE_URL=$base/$($databases[0])",
                "SHOPONLINE_SECRET_KEY=$secret",
                "SHOPONLINE_DATA_DIR=$DataDir",
                "SHOPONLINE_WEB_HOST=127.0.0.1",
                "SHOPONLINE_WEB_PORT=8750"
            )
            if ($Environment -eq "dev") { $lines += "SHOPONLINE_TEST_DATABASE_URL=$base/shoponline_test" }
            $utf8 = New-Object System.Text.UTF8Encoding($false)
            [IO.File]::WriteAllLines($EnvFile, $lines, $utf8)
            New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
            Write-Host "Đã ghi $EnvFile và tạo thư mục $DataDir"
        }
    }
}
finally {
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
}
