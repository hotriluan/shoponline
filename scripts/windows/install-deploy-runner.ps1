<#
.SYNOPSIS
  Install the GitHub Actions self-hosted runner that deploys pushes to main on this machine.

.DESCRIPTION
  Downloads the latest runner release, checks its SHA-256 against the release notes, registers
  it to the repository with label shoponline-prod (registration token from the gh CLI, which
  must be logged in as a repository admin), then registers the Task Scheduler task
  shoponline-deploy-runner that starts the runner when the current user logs on.
  The runner runs as the current user, who owns the production checkout and its scheduled
  tasks, so no admin rights or stored passwords are needed. Rerun to re-register the task;
  an already configured runner folder is kept. The task runs the runner with no window
  (conhost --headless, see settings.ps1) and keeps running on battery.

  With -TaskOnly it needs neither gh nor a download: it only updates the command and settings
  of an existing shoponline-deploy-runner task that differ from the wanted ones, and starts
  nothing. update-production.ps1 calls it this way on every deploy; a runner busy with that
  deploy keeps running and starts the new way at the next logon.

.EXAMPLE
  pwsh -ExecutionPolicy Bypass -File scripts\windows\install-deploy-runner.ps1
#>
param(
    [string]$Repo,
    [string]$RunnerDir = "C:\actions-runner",
    [string]$Name = "$env:COMPUTERNAME-shoponline",
    [string]$Label = "shoponline-prod",
    [switch]$TaskOnly
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "settings.ps1")
$taskName = "shoponline-deploy-runner"
$action = New-HiddenTaskAction -Execute "$RunnerDir\run.cmd" -WorkingDirectory $RunnerDir
$settings = New-TaskSettings -StartWhenAvailable -MultipleInstances IgnoreNew -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)

if ($TaskOnly) {
    $existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if (-not $existing) { Write-Host "Chưa có $taskName, bỏ qua"; return }
    if (Test-TaskMatches $existing $action $settings) {
        Write-Host "Đã có $taskName, giữ nguyên"
        return
    }
    Set-ScheduledTask -TaskName $taskName -Action $action -Settings $settings | Out-Null
    Write-Host "Cập nhật cách chạy $taskName (áp dụng từ lần đăng nhập sau)"
    return
}

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw "Cần gh CLI đã đăng nhập (gh auth login)" }
if (-not $Repo) { $Repo = gh repo view --json nameWithOwner -q .nameWithOwner }
if (-not $Repo) { throw "Không xác định được repo; truyền -Repo owner/name" }

if (Test-Path (Join-Path $RunnerDir ".runner")) {
    Write-Host "Runner đã cấu hình tại $RunnerDir, giữ nguyên"
} else {
    $release = gh api repos/actions/runner/releases/latest | ConvertFrom-Json
    $version = $release.tag_name.TrimStart("v")
    $asset = "actions-runner-win-x64-$version.zip"
    if ($release.body -notmatch "<!-- BEGIN SHA win-x64 -->([0-9a-f]{64})<!-- END SHA win-x64 -->") {
        throw "Không thấy SHA-256 của $asset trong release notes"
    }
    $expected = $Matches[1]
    $zip = Join-Path ([IO.Path]::GetTempPath()) $asset
    Invoke-WebRequest "https://github.com/actions/runner/releases/download/v$version/$asset" -OutFile $zip -UseBasicParsing
    try {
        if ((Get-FileHash $zip -Algorithm SHA256).Hash -ne $expected) { throw "SHA-256 của $asset không khớp" }
        New-Item -ItemType Directory -Force -Path $RunnerDir | Out-Null
        Expand-Archive $zip -DestinationPath $RunnerDir -Force
    } finally {
        Remove-Item $zip -ErrorAction SilentlyContinue
    }
    $token = gh api -X POST "repos/$Repo/actions/runners/registration-token" -q .token
    if (-not $token) { throw "Không lấy được registration token (cần quyền admin repo)" }
    & (Join-Path $RunnerDir "config.cmd") --unattended --url "https://github.com/$Repo" --token $token `
        --name $Name --labels $Label --work _work --replace
    if ($LASTEXITCODE -ne 0) { throw "config.cmd lỗi (mã $LASTEXITCODE)" }
    Write-Host "Đã đăng ký runner $Name ($Label) cho $Repo, phiên bản $version"
}

$user = "$env:USERDOMAIN\$env:USERNAME"
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $taskName -Action $action -Principal $principal `
    -Trigger (New-ScheduledTaskTrigger -AtLogOn -User $user) -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskName $taskName
Write-Host "Đã đăng ký và khởi động shoponline-deploy-runner (chạy khi $user đăng nhập)"
