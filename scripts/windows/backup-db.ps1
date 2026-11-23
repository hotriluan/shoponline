<#
.SYNOPSIS
  Database backup before a deploy: a thin wrapper over `shoponline backup run --kind db`.

.DESCRIPTION
  update-production.ps1 runs the copy of this file that is on disk, so it keeps its contract:
  it calls this script and goes on only when the exit code is 0 or 2.
    0  every place got the backup
    2  some places got it (still a usable backup)
    1  no place got it
    3  another backup held the lock for 20 minutes, so none was made
  The work is done by the Python module (shoponline.backup): pg_dump, 7-Zip AES-256 with hidden
  names, copy to every folder in SHOPONLINE_BACKUP_DIRS, rotation, the record in the database.
  A backup before a deploy stays on this machine and does not go to Google Drive.
  Settings come from environment variables or the repo-root env file.

.EXAMPLE
  pwsh -ExecutionPolicy Bypass -File scripts\windows\backup-db.ps1
#>
param(
    [string]$PgBin = "C:\Program Files\PostgreSQL\16\bin",
    [string]$SevenZip = "C:\Program Files\7-Zip\7z.exe"
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "settings.ps1")
Set-Location $script:RepoRoot

uv run --no-dev --extra robot shoponline backup run --kind db --reason deploy --pg-bin $PgBin --seven-zip $SevenZip
exit $LASTEXITCODE
