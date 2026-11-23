<#
.SYNOPSIS
  Hand the production system over to another machine: build the migration bundle on this (old)
  machine and release it, or undo that.

.DESCRIPTION
  Run in PowerShell 7 inside the repo of the machine that currently runs the system.

  -Prepare  (this machine keeps running) make a full backup with reason "migration" and print
            where it is, on this machine and on Google Drive. Use it to build the new machine
            before the move day (setup-production-machine.ps1 -Bundle <file> -Prepare).

  (none)    move day. Stops on the first step that fails and says what to do next:
              1. no GitHub Actions job is running; write the maintenance marker "migration"
              2. stop and disable the deploy runner, robot, web, backup and restore tasks
              3. final full backup (migration); it must reach this machine AND Google Drive
              4. disable the retention task
              5. remove this machine's runner from the repository and check GitHub agrees
              6. write released.json in the data folder
            The machine stays as it is (nothing is deleted): it is the way back.

  -Rollback bring this machine back: refuses while GitHub still has a runner labelled
            shoponline-prod that is not this machine's; enables the tasks, installs the runner
            again, starts web and robot, removes released.json and the marker.

  The new machine must be loaded with the final bundle: setup-production-machine.ps1
  -Bundle drive:latest (or the file path). Never run web and robot on both machines.

.EXAMPLE
  pwsh -File scripts\windows\server-export.ps1 -Prepare

.EXAMPLE
  pwsh -File scripts\windows\server-export.ps1
#>
param(
    [switch]$Prepare,
    [switch]$Rollback,
    [string]$Repo,
    [string]$RunnerDir = "C:\actions-runner",
    [int]$WaitSeconds = 120
)

$ErrorActionPreference = "Stop"
if ($Prepare -and $Rollback) { throw "Chọn một trong -Prepare hoặc -Rollback" }
. (Join-Path $PSScriptRoot "settings.ps1")
Set-Location $script:RepoRoot
. (Join-Path $PSScriptRoot "service-control.ps1") -WaitSeconds $WaitSeconds

$dataDir = Get-Setting "SHOPONLINE_DATA_DIR" (Join-Path $script:RepoRoot "data")
$releasedFile = Join-Path $dataDir "released.json"
$maintenanceFile = Join-Path $dataDir "maintenance.json"
$runnerName = "$env:COMPUTERNAME-shoponline"
$runnerLabel = "shoponline-prod"
$taskRunner = "shoponline-deploy-runner"
$tasksToStop = @($taskRunner, "shoponline-robot", "shoponline-web", "shoponline-backup", "shoponline-restore")
$allTasks = $tasksToStop + @("shoponline-retention")
$backupPattern = 'shoponline(\.exe)?"?\s+backup(\s|$)'

function Write-Step([string]$text) { Write-Host ""; Write-Host "== $text" -ForegroundColor Cyan }

function Invoke-Native([string]$what) {
    if ($LASTEXITCODE -ne 0) { throw "$what lỗi (mã $LASTEXITCODE)" }
}

function Get-RepoName {
    if ($Repo) { return $Repo }
    $name = gh repo view --json nameWithOwner -q .nameWithOwner
    Invoke-Native "gh repo view"
    if (-not $name) { throw "Không xác định được repo; truyền -Repo owner/name" }
    return $name
}

# Names of every runner GitHub lists with the production label, online or not.
function Get-ProdRunnerNames([string]$repoName) {
    $lines = gh api "repos/$repoName/actions/runners" --paginate --jq '.runners[] | {name: .name, labels: [.labels[].name]} | @json'
    Invoke-Native "gh api runners"
    $found = foreach ($line in @($lines | Where-Object { $_ })) {
        $runner = $line | ConvertFrom-Json
        if ($runner.labels -contains $runnerLabel) { $runner.name }
    }
    return @($found)
}

function Set-Marker {
    New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
    @{ kind = "migration"; pid = $PID; started_at = [DateTime]::UtcNow.ToString("o") } |
        ConvertTo-Json | Set-Content -Path $maintenanceFile -Encoding UTF8
}

function Clear-Marker {
    if (-not (Test-Path $maintenanceFile)) { return }
    try { $marker = Get-Content $maintenanceFile -Raw -Encoding UTF8 | ConvertFrom-Json } catch { return }
    if ($marker.kind -eq "migration") { Remove-Item $maintenanceFile -ErrorAction SilentlyContinue }
}

function Invoke-FullBackup([switch]$RequireDrive) {
    $extra = @()
    if ($RequireDrive) { $extra += "--require-drive" }
    # Out-Host: a function returns what its commands print, and only the exit code is wanted.
    uv run --no-dev --extra robot shoponline backup run --kind full --reason migration @extra | Out-Host
    return $LASTEXITCODE
}

# ---------------------------------------------------------------- -Prepare
if ($Prepare) {
    Write-Step "Bản Toàn bộ để dựng máy mới (máy này vẫn chạy)"
    $code = Invoke-FullBackup
    if ($code -ne 0 -and $code -ne 2) { throw "Sao lưu lỗi (mã $code)" }
    if ($code -eq 2) { Write-Warning "Chỉ một phần nơi nhận được bản sao lưu; xem dòng trên." }
    Write-Host "Trên máy mới: setup-production-machine.ps1 -Bundle <đường dẫn ở trên | drive:latest> -Prepare"
    return
}

# ---------------------------------------------------------------- -Rollback
if ($Rollback) {
    Write-Step "Bật lại máy này"
    $repoName = Get-RepoName
    $others = @(Get-ProdRunnerNames $repoName | Where-Object { $_ -ne $runnerName })
    if ($others.Count -gt 0) {
        throw "GitHub còn runner nhãn $runnerLabel của máy khác ($($others -join ', ')), kể cả đang offline. Gỡ nó (Settings → Actions → Runners) hoặc dừng máy mới trước, nếu không push kế tiếp có thể deploy lên nhầm máy."
    }
    foreach ($name in $allTasks) {
        if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) { Enable-ScheduledTask -TaskName $name | Out-Null }
    }
    & pwsh -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "install-deploy-runner.ps1") -RunnerDir $RunnerDir
    Invoke-Native "Cài lại runner"
    & pwsh -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "service-control.ps1") -Action start
    Invoke-Native "Bật web và robot"
    Remove-Item $releasedFile -ErrorAction SilentlyContinue
    Clear-Marker
    Write-Host "Máy này đã chạy lại. Nếu máy mới đã nhập liệu, sao lưu nó và phục hồi vào máy này trước khi dùng (docs/deployment-guide.md)." -ForegroundColor Yellow
    return
}

# ---------------------------------------------------------------- move day
$step = "bắt đầu"
try {
    $step = "kiểm tra job GitHub Actions"
    Write-Step "1. Không có job Actions đang chạy"
    $repoName = Get-RepoName
    $running = @(gh run list --repo $repoName --status in_progress --json databaseId --jq ".[].databaseId")
    Invoke-Native "gh run list"
    $queued = @(gh run list --repo $repoName --status queued --json databaseId --jq ".[].databaseId")
    Invoke-Native "gh run list"
    if ($running.Count + $queued.Count -gt 0) { throw "Còn job Actions đang chạy hoặc chờ; đợi xong rồi chạy lại" }
    Set-Marker

    $step = "dừng các tác vụ"
    Write-Step "2. Dừng và Disable runner, robot, web, sao lưu, phục hồi"
    foreach ($name in $tasksToStop) {
        if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) {
            Disable-ScheduledTask -TaskName $name | Out-Null
            Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
        }
    }
    # The runner task ends only its wrapper; the listener and any job worker keep running.
    Get-Process -Name "Runner.Listener", "Runner.Worker" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Stop-Robot
    Stop-Web
    $deadline = (Get-Date).AddSeconds($WaitSeconds)
    while ($busy = Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'uv.exe'" |
            Where-Object { $_.CommandLine -match $backupPattern }) {
        if ((Get-Date) -gt $deadline) { throw "Tiến trình sao lưu hoặc phục hồi vẫn chạy sau $WaitSeconds giây (PID $($busy.ProcessId -join ', '))" }
        Start-Sleep -Seconds 2
    }

    $step = "sao lưu bản cuối"
    Write-Step "3. Bản Toàn bộ cuối (phải tới máy chủ và Google Drive)"
    $code = Invoke-FullBackup -RequireDrive
    if ($code -ne 0) { throw "Bản sao lưu cuối chưa tới đủ cả máy chủ và Google Drive (mã $code)" }

    $step = "tắt tác vụ dọn dữ liệu"
    Write-Step "4. Tắt shoponline-retention"
    if (Get-ScheduledTask -TaskName "shoponline-retention" -ErrorAction SilentlyContinue) {
        Disable-ScheduledTask -TaskName "shoponline-retention" | Out-Null
    }

    $step = "gỡ runner"
    Write-Step "5. Gỡ runner $runnerName khỏi $repoName"
    if (Test-Path (Join-Path $RunnerDir "config.cmd")) {
        $token = gh api -X POST "repos/$repoName/actions/runners/remove-token" -q .token
        Invoke-Native "gh remove-token"
        & (Join-Path $RunnerDir "config.cmd") remove --token $token
        Invoke-Native "config.cmd remove"
    } else {
        Write-Host "Không có $RunnerDir\config.cmd; kiểm tra GitHub bên dưới"
    }
    $left = @(Get-ProdRunnerNames $repoName | Where-Object { $_ -eq $runnerName })
    if ($left.Count -gt 0) { throw "GitHub vẫn còn runner $runnerName; gỡ tay (Settings → Actions → Runners)" }

    $step = "ghi trạng thái đã nhả"
    Write-Step "6. Ghi $releasedFile"
    @{ released_at = [DateTime]::UtcNow.ToString("o"); machine = $env:COMPUTERNAME } |
        ConvertTo-Json | Set-Content -Path $releasedFile -Encoding UTF8
    Clear-Marker
    Write-Host ""
    Write-Host "Đã nhả máy này. Trên máy mới: setup-production-machine.ps1 -Bundle drive:latest" -ForegroundColor Green
    Write-Host "Máy này chỉ tắt, không xóa gì. Lùi lại: pwsh -File scripts\windows\server-export.ps1 -Rollback"
}
catch {
    Write-Error "Dừng ở bước '$step': $_"
    Write-Host "Máy này có thể đang ở trạng thái dừng một phần. Bật lại: pwsh -File scripts\windows\server-export.ps1 -Rollback" -ForegroundColor Yellow
    exit 1
}
