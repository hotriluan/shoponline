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
  4. Fast-forward to the commit, uv sync without dev tools, migrate.
  5. Register the Task Scheduler jobs that are still missing, for the account running this
     script (register-tasks.ps1 -AtLogOn -OnlyMissing): web, backup, retention, robot.
  6. Start shoponline-web and wait until the login page answers. Start shoponline-robot when
     the SAP login settings are present; otherwise warn with the names of the missing ones.
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
$port = [int](Get-Setting "SHOPONLINE_WEB_PORT" "8750")
$webHost = Get-Setting "SHOPONLINE_WEB_HOST" "127.0.0.1"
if ($webHost -eq "0.0.0.0") { $webHost = "127.0.0.1" }
$loginUrl = "http://${webHost}:$port/login"
$me = "$env:USERDOMAIN\$env:USERNAME"
$robotSettings = "SHOPONLINE_SAP_CONNECTION", "SHOPONLINE_SAP_USER", "SHOPONLINE_SAP_PASSWORD"
$robotPattern = 'shoponline(\.exe)?"?\s+robot(\s|$)'

function Invoke-Native([string]$what) {
    if ($LASTEXITCODE -ne 0) { throw "$what lỗi (mã $LASTEXITCODE)" }
}

function Test-WebUp {
    try { return (Invoke-WebRequest $loginUrl -UseBasicParsing -TimeoutSec 5).StatusCode -eq 200 }
    catch { return $false }
}

function Stop-Web {
    Stop-ScheduledTask -TaskName "shoponline-web"
    # Stopping the task ends only its wrapper; the Python processes it started keep the port.
    # Stop the web processes of this checkout's venv (the venv launcher and its child).
    $venvWeb = [regex]::Escape((Join-Path $script:RepoRoot ".venv\Scripts\shoponline.exe")) + '"?\s+web(\s|$)'
    $deadline = (Get-Date).AddSeconds($WaitSeconds)
    while ((Get-Date) -lt $deadline) {
        Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
            Where-Object { $_.CommandLine -match $venvWeb } |
            ForEach-Object { Stop-Process -Id $_.ProcessId -ErrorAction SilentlyContinue }
        if (-not (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)) { return }
        Start-Sleep -Seconds 1
    }
    throw "Cổng $port vẫn bị giữ sau $WaitSeconds giây; kiểm tra tiến trình đang nghe cổng đó"
}

function Start-Web {
    Start-ScheduledTask -TaskName "shoponline-web"
    $deadline = (Get-Date).AddSeconds($WaitSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-WebUp) { return }
        Start-Sleep -Seconds 2
    }
    throw "Web không trả lời $loginUrl sau $WaitSeconds giây"
}

function Get-RobotProcess {
    Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'uv.exe'" |
        Where-Object { $_.CommandLine -match $robotPattern }
}

function Stop-Robot {
    if (Get-ScheduledTask -TaskName "shoponline-robot" -ErrorAction SilentlyContinue) {
        Stop-ScheduledTask -TaskName "shoponline-robot"
    }
    # A job cut off here goes back to the queue when the robot starts again.
    $deadline = (Get-Date).AddSeconds($WaitSeconds)
    while ($running = Get-RobotProcess) {
        if ((Get-Date) -gt $deadline) { throw "Robot vẫn chạy sau $WaitSeconds giây (PID $($running.ProcessId -join ', '))" }
        $running | ForEach-Object { Stop-Process -Id $_.ProcessId -ErrorAction SilentlyContinue }
        Start-Sleep -Seconds 1
    }
}

function Register-MissingTasks {
    $register = Join-Path $PSScriptRoot "register-tasks.ps1"
    & pwsh -NoProfile -ExecutionPolicy Bypass -File $register -User $me -AtLogOn -OnlyMissing -WebPort $port
    Invoke-Native "Đăng ký tác vụ"
    & pwsh -NoProfile -ExecutionPolicy Bypass -File $register -RobotUser $me -OnlyMissing
    Invoke-Native "Đăng ký tác vụ robot"
}

# Returns $false when the robot should run but does not; missing SAP settings only warn.
function Start-Robot {
    $missing = $robotSettings | Where-Object { -not (Get-Setting $_) }
    if ($missing) {
        Write-Warning "Robot chưa chạy: thiếu cấu hình $($missing -join ', ') (xem docs/robot-machine-setup.md)"
        return $true
    }
    if (Get-RobotProcess) { Write-Host "Robot đang chạy"; return $true }
    Start-ScheduledTask -TaskName "shoponline-robot"
    # A robot that cannot start (bad settings, a second robot) exits within seconds.
    Start-Sleep -Seconds 20
    if (Get-RobotProcess) { Write-Host "Đã khởi động robot"; return $true }
    $dataDir = Get-Setting "SHOPONLINE_DATA_DIR" (Join-Path $script:RepoRoot "data")
    Write-Warning "Robot dừng ngay sau khi khởi động; xem $(Join-Path $dataDir 'logs\robot.log') hoặc chạy tay: uv run --no-dev --extra robot shoponline robot"
    return $false
}

function Complete-Deploy {
    Register-MissingTasks
    if (-not (Test-WebUp)) { Start-Web }
    if (-not (Start-Robot)) { throw "Robot không khởi động được" }
}

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
try {
    Stop-Robot
    Stop-Web
    & pwsh -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "backup-db.ps1")
    # Exit code 2: the backup reached some but not all folders; still a usable backup.
    if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne 2) { throw "Sao lưu lỗi (mã $LASTEXITCODE)" }
    git merge --ff-only --quiet $target; Invoke-Native "git merge"
    uv sync --frozen --no-dev --extra robot; Invoke-Native "uv sync"
    uv run --no-dev shoponline migrate; Invoke-Native "migrate"
    Complete-Deploy
    Write-Host "Đã triển khai $target"
}
catch {
    Write-Warning "Triển khai lỗi: $_"
    Write-Warning "Bản trước: $previous. Lùi lại: git reset --hard $previous; uv sync --frozen --no-dev --extra robot; khôi phục bản sao lưu nếu schema đã đổi."
    if (-not (Test-WebUp)) {
        try { Start-Web } catch { Write-Warning "Không khởi động lại được web: $_" }
    }
    try { $null = Start-Robot } catch { Write-Warning "Không khởi động lại được robot: $_" }
    throw
}
