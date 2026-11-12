<#
.SYNOPSIS
  Update the production checkout to a commit on origin/main: stop web, back up, pull, migrate, start.

.DESCRIPTION
  Run inside the production checkout (the deploy workflow calls it on the self-hosted runner).
  1. Refuse when the checkout has local edits or the commit is not on origin/main.
  2. Stop the shoponline-web task and wait until the web port is free.
  3. Back up the database (backup-db.ps1) before any schema change.
  4. Fast-forward to the commit, uv sync without dev tools, migrate.
  5. Start shoponline-web and wait until the login page answers.
  On failure it still tries to start the web and prints the previous commit for a rollback.
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

function Invoke-Native([string]$what) {
    if ($LASTEXITCODE -ne 0) { throw "$what lỗi (mã $LASTEXITCODE)" }
}

function Test-WebUp {
    try { return (Invoke-WebRequest $loginUrl -UseBasicParsing -TimeoutSec 5).StatusCode -eq 200 }
    catch { return $false }
}

function Stop-Web {
    Stop-ScheduledTask -TaskName "shoponline-web"
    $deadline = (Get-Date).AddSeconds($WaitSeconds)
    while ((Get-Date) -lt $deadline) {
        $listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        if (-not $listener) { return }
        # Only a process running from this checkout is ours to stop.
        $owner = Get-Process -Id $listener[0].OwningProcess -ErrorAction SilentlyContinue
        if ($owner -and $owner.Path -and $owner.Path.StartsWith($script:RepoRoot, [StringComparison]::OrdinalIgnoreCase)) {
            Stop-Process -Id $owner.Id
        }
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

if (git status --porcelain --untracked-files=no) { throw "Thư mục $script:RepoRoot có sửa đổi cục bộ; không cập nhật" }
git fetch --quiet origin main; Invoke-Native "git fetch"
$target = (git rev-parse --verify "$Commit^{commit}"); Invoke-Native "git rev-parse"
git merge-base --is-ancestor $target origin/main
if ($LASTEXITCODE -ne 0) { throw "Commit $Commit không nằm trên origin/main" }
$previous = (git rev-parse HEAD)

if ($previous -eq $target) {
    Write-Host "Đã ở $target"
    if (-not (Test-WebUp)) { Start-Web }
    return
}
git merge-base --is-ancestor HEAD $target
if ($LASTEXITCODE -ne 0) { throw "Commit $Commit cũ hơn bản đang chạy $previous; không lùi phiên bản tự động" }

Write-Host "Cập nhật $previous -> $target"
try {
    Stop-Web
    & pwsh -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "backup-db.ps1")
    # Exit code 2: the backup reached some but not all folders; still a usable backup.
    if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne 2) { throw "Sao lưu lỗi (mã $LASTEXITCODE)" }
    git merge --ff-only --quiet $target; Invoke-Native "git merge"
    uv sync --frozen --no-dev; Invoke-Native "uv sync"
    uv run --no-dev shoponline migrate; Invoke-Native "migrate"
    Start-Web
    Write-Host "Đã triển khai $target"
}
catch {
    Write-Warning "Triển khai lỗi: $_"
    Write-Warning "Bản trước: $previous. Lùi lại: git reset --hard $previous; uv sync --frozen --no-dev; khôi phục bản sao lưu nếu schema đã đổi."
    if (-not (Test-WebUp)) {
        try { Start-Web } catch { Write-Warning "Không khởi động lại được web: $_" }
    }
    throw
}
