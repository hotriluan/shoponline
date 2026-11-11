<#
.SYNOPSIS
  Encrypted daily backup of the shoponline database to one or more folders outside the machine.

.DESCRIPTION
  1. pg_dump (custom format) of the database in SHOPONLINE_DATABASE_URL.
  2. Encrypt with 7-Zip AES-256 (file names hidden too) using SHOPONLINE_BACKUP_PASSWORD.
  3. Copy to every folder in SHOPONLINE_BACKUP_DIRS (separated by ';'), e.g. the company
     network share and the Google Drive for desktop folder.
  4. Delete backups older than SHOPONLINE_BACKUP_KEEP_DAYS (default 30) in those folders.
  5. Write the time to <SHOPONLINE_DATA_DIR>\last-backup.txt; the web warns after 36 hours.
  Settings come from environment variables, or from the repo-root env file when not set.
  The encryption password must live in the secret store, never next to the backups.

.EXAMPLE
  pwsh -ExecutionPolicy Bypass -File scripts\windows\backup-db.ps1
#>
param(
    [string]$PgBin = "C:\Program Files\PostgreSQL\16\bin",
    [string]$SevenZip = "C:\Program Files\7-Zip\7z.exe"
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "settings.ps1")

$dbUrl = Get-Setting "SHOPONLINE_DATABASE_URL"
$password = Get-Setting "SHOPONLINE_BACKUP_PASSWORD"
$targets = (Get-Setting "SHOPONLINE_BACKUP_DIRS").Split(";") | Where-Object { $_.Trim() } | ForEach-Object { $_.Trim() }
$keepDays = [int](Get-Setting "SHOPONLINE_BACKUP_KEEP_DAYS" "30")
$dataDir = Get-Setting "SHOPONLINE_DATA_DIR"

if (-not $dbUrl) { throw "Thiếu SHOPONLINE_DATABASE_URL" }
if (-not $password) { throw "Thiếu SHOPONLINE_BACKUP_PASSWORD" }
if (-not $targets) { throw "Thiếu SHOPONLINE_BACKUP_DIRS" }
if (-not $dataDir) { throw "Thiếu SHOPONLINE_DATA_DIR" }
if (-not (Test-Path $SevenZip)) { throw "Không thấy 7-Zip tại $SevenZip" }

$db = ConvertFrom-DatabaseUrl $dbUrl
$pgUser = $db.User; $pgHost = $db.Host; $pgPort = $db.Port; $pgDb = $db.Database
$env:PGPASSWORD = $db.Password

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$work = Join-Path ([IO.Path]::GetTempPath()) "shoponline-backup-$stamp"
New-Item -ItemType Directory -Path $work | Out-Null
try {
    $dump = Join-Path $work "$pgDb-$stamp.dump"
    & (Join-Path $PgBin "pg_dump.exe") -h $pgHost -p $pgPort -U $pgUser -d $pgDb -Fc -f $dump
    if ($LASTEXITCODE -ne 0) { throw "pg_dump lỗi" }

    $archive = Join-Path $work "shoponline-$pgDb-$stamp.7z"
    & $SevenZip a -t7z -mhe=on "-p$password" $archive $dump | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "7-Zip lỗi khi mã hóa" }
    & $SevenZip t "-p$password" $archive | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Kiểm tra bản mã hóa thất bại" }

    $copied = 0
    foreach ($target in $targets) {
        try {
            New-Item -ItemType Directory -Force -Path $target | Out-Null
            Copy-Item $archive $target
            Get-ChildItem $target -Filter "shoponline-$pgDb-*.7z" |
                Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$keepDays) } |
                Remove-Item
            Write-Host "Đã chép tới $target"
            $copied++
        } catch {
            Write-Warning "Không chép được tới ${target}: $_"
        }
    }
    if ($copied -eq 0) { throw "Không chép được bản sao lưu tới nơi nào" }
    if ($copied -lt $targets.Count) {
        Write-Warning "Chỉ chép được tới $copied/$($targets.Count) nơi; không ghi mốc sao lưu"
        exit 2
    }
    New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
    Set-Content -Path (Join-Path $dataDir "last-backup.txt") -Value ((Get-Date).ToUniversalTime().ToString("o")) -Encoding UTF8
    Write-Host "Sao lưu xong: $(Split-Path $archive -Leaf)"
}
finally {
    Remove-Item -Recurse -Force $work -ErrorAction SilentlyContinue
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
}
