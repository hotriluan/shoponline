<#
.SYNOPSIS
  Update the production checkout to a commit on origin/main: stop web and robot, back up, pull,
  migrate, register missing tasks, start web and robot.

.DESCRIPTION
  Run inside the production checkout (the deploy workflow calls it on the self-hosted runner).
  1. Refuse when the checkout has local edits or the commit is not on origin/main.
  2. Stop the shoponline-robot task (the robot holds pywin32 files that uv sync replaces) and
     the shoponline-web task, and wait until the web port is free.
  3. Back up the database (backup-db.ps1) before any schema change.
  Web and robot are stopped and started through service-control.ps1. While a deploy works it
  keeps a marker file (maintenance.json) and refuses to start when a restore is running.
  4. Disable and stop the backup and restore tasks (their Python processes hold files of the
     venv that uv sync replaces), fast-forward to the commit, uv sync without dev tools,
     migrate. The tasks are enabled again when the deploy ends, also when it fails.
  5. Register the Task Scheduler jobs that are still missing, and update the command of those
     that run differently from what register-tasks.ps1 now registers, for the account running
     this script (register-tasks.ps1 -AtLogOn -OnlyMissing): web, backup, retention, robot; and
     the runner's own task (install-deploy-runner.ps1 -TaskOnly).
  6. Start shoponline-web and wait until the login page answers, then shoponline-robot. The
     robot starts even with no SAP settings; the web page "Kết nối SAP" shows what is missing.
  Steps 5 and 6 also run when the checkout is already at the commit, so re-running the
  workflow repairs missing tasks. On failure it still tries to start web and robot and prints
  the previous commit for a rollback.
  The script runs from the copy already on disk, so a change to this file applies from the
  next deploy.

.EXAMPLE
  pwsh -File scripts\windows\update-production.ps1 -Commit 0123abcd
#>
param(
    [Parameter(Mandatory = $true)][string]$Commit,
    [int]$WaitSeconds = 60
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "settings.ps1")
Set-Location $script:RepoRoot
$me = "$env:USERDOMAIN\$env:USERNAME"

. (Join-Path $PSScriptRoot "service-control.ps1") -WaitSeconds $WaitSeconds

function Invoke-Native([string]$what) {
    if ($LASTEXITCODE -ne 0) { throw "$what lỗi (mã $LASTEXITCODE)" }
}

# A deploy and a restore must never run together. Each writes a marker file while it works
# (shoponline.backup.maintenance reads the same file); a marker older than 2 hours is stale.
$maintenanceFile = Join-Path (Get-Setting "SHOPONLINE_DATA_DIR" (Join-Path $script:RepoRoot "data")) "maintenance.json"

function Test-RestoreRunning {
    if (-not (Test-Path $maintenanceFile)) { return $false }
    try { $marker = Get-Content $maintenanceFile -Raw -Encoding UTF8 | ConvertFrom-Json } catch { return $false }
    if ($marker.kind -ne "restore") { return $false }
    return ([DateTime]::UtcNow - [DateTime]::Parse($marker.started_at).ToUniversalTime()) -lt [TimeSpan]::FromHours(2)
}

function Set-DeployMarker {
    New-Item -ItemType Directory -Force -Path (Split-Path $maintenanceFile) | Out-Null
    @{ kind = "deploy"; pid = $PID; started_at = [DateTime]::UtcNow.ToString("o") } |
        ConvertTo-Json | Set-Content -Path $maintenanceFile -Encoding UTF8
}

function Clear-DeployMarker {
    if (-not (Test-Path $maintenanceFile)) { return }
    try { $marker = Get-Content $maintenanceFile -Raw -Encoding UTF8 | ConvertFrom-Json } catch { return }
    if ($marker.kind -eq "deploy") { Remove-Item $maintenanceFile -ErrorAction SilentlyContinue }
}

# The backup and restore tasks run the venv's Python, which uv sync replaces. Stop them for the
# update and enable them again afterwards. A task that is not registered yet is skipped.
$script:BackupTaskNames = @("shoponline-backup", "shoponline-restore")
$backupPattern = 'shoponline(\.exe)?"?\s+backup(\s|$)'

function Suspend-BackupTasks {
    foreach ($name in $script:BackupTaskNames) {
        if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) {
            Disable-ScheduledTask -TaskName $name | Out-Null
            Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
        }
    }
    $deadline = (Get-Date).AddSeconds($WaitSeconds)
    while ($running = Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'uv.exe'" |
            Where-Object { $_.CommandLine -match $backupPattern }) {
        if ((Get-Date) -gt $deadline) { throw "Tiến trình sao lưu vẫn chạy sau $WaitSeconds giây (PID $($running.ProcessId -join ', '))" }
        $running | ForEach-Object { Stop-Process -Id $_.ProcessId -ErrorAction SilentlyContinue }
        Start-Sleep -Seconds 1
    }
}

function Resume-BackupTasks {
    foreach ($name in $script:BackupTaskNames) {
        if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) {
            Enable-ScheduledTask -TaskName $name | Out-Null
        }
    }
}

function Register-MissingTasks {
    $register = Join-Path $PSScriptRoot "register-tasks.ps1"
    & pwsh -NoProfile -ExecutionPolicy Bypass -File $register -User $me -AtLogOn -OnlyMissing -WebPort $port
    Invoke-Native "Đăng ký tác vụ"
    & pwsh -NoProfile -ExecutionPolicy Bypass -File $register -RobotUser $me -OnlyMissing
    Invoke-Native "Đăng ký tác vụ robot"
    & pwsh -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "install-deploy-runner.ps1") -TaskOnly
    Invoke-Native "Cập nhật tác vụ runner"
}


function Complete-Deploy {
    Register-MissingTasks
    Resume-BackupTasks
    if (-not (Test-WebUp)) { Start-Web }
    if (-not (Start-Robot)) { throw "Robot không khởi động được" }
}

if (Test-RestoreRunning) { throw "Đang có phục hồi dữ liệu chạy (xem $maintenanceFile); không triển khai lúc này, thử lại sau" }
if (git status --porcelain --untracked-files=no) { throw "Thư mục $script:RepoRoot có sửa đổi cục bộ; không cập nhật" }
git fetch --quiet origin main; Invoke-Native "git fetch"
$target = (git rev-parse --verify "$Commit^{commit}"); Invoke-Native "git rev-parse"
git merge-base --is-ancestor $target origin/main
if ($LASTEXITCODE -ne 0) { throw "Commit $Commit không nằm trên origin/main" }
$previous = (git rev-parse HEAD)

if ($previous -eq $target) {
    Write-Host "Đã ở $target"
    Complete-Deploy
    return
}
git merge-base --is-ancestor HEAD $target
if ($LASTEXITCODE -ne 0) { throw "Commit $Commit cũ hơn bản đang chạy $previous; không lùi phiên bản tự động" }

Write-Host "Cập nhật $previous -> $target"
Set-DeployMarker
try {
    Stop-Robot
    Stop-Web
    & pwsh -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "backup-db.ps1")
    # Exit code 2: the backup reached some but not all folders; still a usable backup.
    # Exit code 3: another backup held the lock for 20 minutes, so none was made.
    if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne 2) { throw "Sao lưu lỗi (mã $LASTEXITCODE)" }
    Suspend-BackupTasks
    git merge --ff-only --quiet $target; Invoke-Native "git merge"
    uv sync --frozen --no-dev --extra robot; Invoke-Native "uv sync"
    uv run --no-dev shoponline migrate; Invoke-Native "migrate"
    Complete-Deploy
    Write-Host "Đã triển khai $target"
}
catch {
    Write-Warning "Triển khai lỗi: $_"
    try { Resume-BackupTasks } catch { Write-Warning "Không bật lại được tác vụ sao lưu: $_" }
    Write-Warning "Bản trước: $previous. Lùi lại: git reset --hard $previous; uv sync --frozen --no-dev --extra robot; khôi phục bản sao lưu nếu schema đã đổi."
    if (-not (Test-WebUp)) {
        try { Start-Web } catch { Write-Warning "Không khởi động lại được web: $_" }
    }
    try { $null = Start-Robot } catch { Write-Warning "Không khởi động lại được robot: $_" }
    throw
}
finally {
    Clear-DeployMarker
}
