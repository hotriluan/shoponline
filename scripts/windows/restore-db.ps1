<#
.SYNOPSIS
  Restore an encrypted shoponline backup into a target database (for drills and recovery).

.DESCRIPTION
  Decrypts the .7z made by backup-db.ps1 and runs pg_restore --clean --if-exists into the
  database named by the setting -TargetSetting (an environment variable or a line in the
  repo-root env file holding a postgresql:// URL), so no password is typed on the command line.
  The backup password comes from SHOPONLINE_BACKUP_PASSWORD or is asked for.
  Refuses a target database named exactly "shoponline" unless -AllowProduction is given.

.EXAMPLE
  pwsh -File scripts\windows\restore-db.ps1 -Archive \\share\backup\shoponline-shoponline-20261111-230000.7z `
       -TargetSetting SHOPONLINE_RESTORE_DATABASE_URL
#>
param(
    [Parameter(Mandatory = $true)][string]$Archive,
    [string]$TargetSetting = "SHOPONLINE_RESTORE_DATABASE_URL",
    [switch]$AllowProduction,
    [string]$PgBin = "C:\Program Files\PostgreSQL\16\bin",
    [string]$SevenZip = "C:\Program Files\7-Zip\7z.exe"
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "settings.ps1")

$targetUrl = Get-Setting $TargetSetting
if (-not $targetUrl) { throw "Thiếu $TargetSetting" }
$db = ConvertFrom-DatabaseUrl $targetUrl
if ($db.Database -eq "shoponline" -and -not $AllowProduction) {
    throw "Từ chối ghi đè database thật khi thiếu -AllowProduction"
}

$password = Get-Setting "SHOPONLINE_BACKUP_PASSWORD"
if (-not $password) {
    $secure = Read-Host -Prompt "Mật khẩu bản sao lưu" -AsSecureString
    $password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
}

$work = Join-Path ([IO.Path]::GetTempPath()) ("shoponline-restore-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $work | Out-Null
try {
    & $SevenZip x "-p$password" "-o$work" $Archive | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Giải mã thất bại (sai mật khẩu hoặc file hỏng)" }
    $dump = Get-ChildItem $work -Filter *.dump | Select-Object -First 1
    if (-not $dump) { throw "Không có file .dump trong bản sao lưu" }
    $env:PGPASSWORD = $db.Password
    & (Join-Path $PgBin "pg_restore.exe") -h $db.Host -p $db.Port -U $db.User -d $db.Database `
        --clean --if-exists --no-owner $dump.FullName
    if ($LASTEXITCODE -ne 0) { throw "pg_restore lỗi" }
    $count = & (Join-Path $PgBin "psql.exe") -h $db.Host -p $db.Port -U $db.User -d $db.Database `
        -tAc "SELECT count(*) FROM platform_setting"
    Write-Host "Khôi phục xong vào $($db.Database); platform_setting có $count dòng"
}
finally {
    Remove-Item -Recurse -Force $work -ErrorAction SilentlyContinue
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
}
