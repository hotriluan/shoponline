<#
.SYNOPSIS
  Register the Task Scheduler jobs on the production machine: web at startup, the backup task
  (every 15 minutes, runs what the schedule on the web page Sao lưu says is due), daily data
  file retention (customer data is kept for good).

.DESCRIPTION
  Run from an elevated PowerShell 7 on the production machine, inside the repo folder.
  Tasks run as -User (the account that owns the repo, env file and data folder).
  Every task runs with no window (conhost --headless, see settings.ps1) and keeps running on
  battery. Refuses to register a new web task when something already listens on the web port,
  so no second web process is started next to a stale one.

  With -RobotUser it registers only the SAP robot task instead: it starts when that account
  logs on (the robot needs the account's desktop for SAP GUI) and never runs twice at once.
  Run it after the robot machine is set up as in docs/robot-machine-setup.md.

  With -OnlyMissing it registers the tasks that do not exist yet, and updates the command and
  battery settings of existing tasks that differ from what this script would register. Their
  triggers and account are kept, with one narrow exception: the
  trigger of shoponline-backup is replaced when it is not the 15-minute repetition (a machine
  that still has the old daily trigger). It starts nothing.
  update-production.ps1 calls it this way on every deploy.

.EXAMPLE
  pwsh -ExecutionPolicy Bypass -File scripts\windows\register-tasks.ps1 -User MAYCHU\shoponline

.EXAMPLE
  pwsh -ExecutionPolicy Bypass -File scripts\windows\register-tasks.ps1 -User $env:USERDOMAIN\$env:USERNAME -AtLogOn

.EXAMPLE
  pwsh -ExecutionPolicy Bypass -File scripts\windows\register-tasks.ps1 -RobotUser MAYCHU\saprobot
#>
param(
    [string]$User,
    [string]$RobotUser,
    # No longer used: the backup times are set on the web page Sao lưu. Still accepted so an old
    # command line keeps working.
    [string]$BackupTime = "",
    # Run web and backup in -User's session when that user logs on (no stored password, no
    # admin rights needed when -User is the current user). For a machine one person logs on to.
    [switch]$AtLogOn,
    # The daily retention task only lists what is past SHOPONLINE_RETENTION_DAYS until this is
    # passed; turn it on after someone has reviewed a week of data\logs\retention.log.
    [switch]$RetentionApply,
    [string]$RetentionTime = "12:30",
    [switch]$OnlyMissing,
    [int]$WebPort = 8750,
    [string]$Uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "settings.ps1")
$repoRoot = $script:RepoRoot
if (-not $Uv) { throw "Không thấy uv; truyền -Uv <đường dẫn uv.exe>" }

# What to do with task $name given the wanted action and settings:
#   "new"    - register it (always, without -OnlyMissing);
#   "update" - it exists but runs another command or stops on battery: replace those, keep the rest;
#   "keep"   - it exists as wanted.
function Get-TaskChange([string]$name, $action, $settings) {
    if (-not $OnlyMissing) { return "new" }
    $existing = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if (-not $existing) { return "new" }
    if (Test-TaskMatches $existing $action $settings) {
        Write-Host "Đã có $name, giữ nguyên"
        return "keep"
    }
    return "update"
}

# Replace the command and settings of an existing task; its triggers and account stay as they are.
# A running instance keeps going; the new command applies from its next start.
function Update-TaskCommand([string]$name, $action, $settings) {
    Set-ScheduledTask -TaskName $name -Action $action -Settings $settings | Out-Null
    Write-Host "Cập nhật cách chạy $name"
}

if ($RobotUser) {
    $robotAction = New-HiddenTaskAction -Execute $Uv -Argument "run --no-dev --extra robot shoponline robot" -WorkingDirectory $repoRoot
    $robotSettings = New-TaskSettings -MultipleInstances IgnoreNew -RestartCount 3 `
        -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
    $change = Get-TaskChange "shoponline-robot" $robotAction $robotSettings
    if ($change -eq "keep") { return }
    # Task Scheduler never starts a second robot (IgnoreNew), so a running robot may get its
    # command updated; a fresh registration still requires it stopped.
    if ($change -eq "update") { Update-TaskCommand "shoponline-robot" $robotAction $robotSettings; return }
    $running = Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'uv.exe'" |
        Where-Object { $_.CommandLine -match 'shoponline(\.exe)?"?\s+robot(\s|$)' }
    if ($running) {
        throw "Robot đang chạy (PID $($running.ProcessId -join ', ')). Dừng nó trước khi đăng ký lại."
    }
    $robotPrincipal = New-ScheduledTaskPrincipal -UserId $RobotUser -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName "shoponline-robot" -Action $robotAction `
        -Trigger (New-ScheduledTaskTrigger -AtLogOn -User $RobotUser) -Principal $robotPrincipal `
        -Settings $robotSettings -Force | Out-Null
    Write-Host "Đã đăng ký shoponline-robot (chạy khi $RobotUser đăng nhập)"
    return
}
if (-not $User) { throw "Truyền -User (web và sao lưu) hoặc -RobotUser (robot SAP)" }
if ($BackupTime) { Write-Warning "-BackupTime không còn tác dụng: giờ sao lưu nay đặt trên trang Sao lưu của web." }
if ($OnlyMissing -and -not $AtLogOn) { throw "-OnlyMissing chỉ dùng cùng -AtLogOn (không hỏi mật khẩu)" }

if ($RetentionApply) { Write-Warning "-RetentionApply không còn tác dụng: dữ liệu khách được giữ, tác vụ chỉ dọn file hết dùng." }
$retentionArgs = "retention"

$settings = New-TaskSettings -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
$dailySettings = New-TaskSettings -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1)
# One run at a time (a second start while a backup runs is ignored); a full backup can be long.
$backupSettings = New-TaskSettings -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 3)
$webAction = New-HiddenTaskAction -Execute $Uv -Argument "run --no-dev shoponline web" -WorkingDirectory $repoRoot
$backupAction = New-HiddenTaskAction -Execute $Uv -Argument "run --no-dev --extra robot shoponline backup run --if-due" -WorkingDirectory $repoRoot
# Started on demand by the web page Sao lưu (schtasks /Run), never by a trigger. It takes the
# backup lock and works through one restore request, so the web that asked can be stopped.
$restoreSettings = New-TaskSettings -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 1)
$restoreAction = New-HiddenTaskAction -Execute $Uv -Argument "run --no-dev --extra robot shoponline backup process-queue --restore" -WorkingDirectory $repoRoot
$retentionAction = New-HiddenTaskAction -Execute $Uv -Argument "run --no-dev shoponline $retentionArgs" -WorkingDirectory $repoRoot

$tasks = @(
    @{ Name = "shoponline-web"; Action = $webAction; Settings = $settings },
    @{ Name = "shoponline-backup"; Action = $backupAction; Settings = $backupSettings },
    @{ Name = "shoponline-restore"; Action = $restoreAction; Settings = $restoreSettings },
    @{ Name = "shoponline-retention"; Action = $retentionAction; Settings = $dailySettings }
)
foreach ($task in $tasks) {
    $task.Change = Get-TaskChange $task.Name $task.Action $task.Settings
    if ($task.Change -eq "update") { Update-TaskCommand $task.Name $task.Action $task.Settings }
}
$isNew = @{}
foreach ($task in $tasks) { $isNew[$task.Name] = $task.Change -eq "new" }

# The backup task wakes every 15 minutes and asks the database what is due, so changing a time
# on the web needs no re-registration. An older machine still has the daily trigger.
function New-BackupTrigger {
    New-ScheduledTaskTrigger -Once -At (Get-Date).Date -RepetitionInterval (New-TimeSpan -Minutes 15) `
        -RepetitionDuration (New-TimeSpan -Days 3650)
}
if ($OnlyMissing -and -not $isNew["shoponline-backup"]) {
    $backupTask = Get-ScheduledTask -TaskName "shoponline-backup"
    $repeat = $backupTask.Triggers | Where-Object { $_.Repetition.Interval -eq "PT15M" }
    if (-not $repeat) {
        Set-ScheduledTask -TaskName "shoponline-backup" -Trigger (New-BackupTrigger) | Out-Null
        Write-Host "shoponline-backup nay chạy mỗi 15 phút (giờ sao lưu đặt trên trang Sao lưu)"
    }
}
if (-not ($isNew.Values -contains $true)) { return }

$listening = Get-NetTCPConnection -LocalPort $WebPort -State Listen -ErrorAction SilentlyContinue
if ($listening -and $isNew["shoponline-web"]) {
    $owner = Get-Process -Id $listening[0].OwningProcess -ErrorAction SilentlyContinue
    throw "Cổng $WebPort đang được $($owner.ProcessName) (PID $($listening[0].OwningProcess)) dùng. Dừng tiến trình đó hoặc đổi SHOPONLINE_WEB_PORT trước."
}

if ($AtLogOn) {
    # Single-user machine: tasks run in the user's session, so no password is stored.
    $account = @{ Principal = New-ScheduledTaskPrincipal -UserId $User -LogonType Interactive -RunLevel Limited }
    $webTrigger = New-ScheduledTaskTrigger -AtLogOn -User $User
    $webWhen = "khi $User đăng nhập"
} else {
    $secure = Read-Host -Prompt "Mật khẩu Windows của $User" -AsSecureString
    $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
    $account = @{ User = $User; Password = $plain; RunLevel = "Limited" }
    $webTrigger = New-ScheduledTaskTrigger -AtStartup
    $webWhen = "khi máy khởi động"
}

if ($isNew["shoponline-web"]) {
    Register-ScheduledTask -TaskName "shoponline-web" -Action $webAction -Trigger $webTrigger `
        -Settings $settings @account -Force | Out-Null
    Write-Host "Đã đăng ký shoponline-web (chạy $webWhen)"
}

if ($isNew["shoponline-backup"]) {
    Register-ScheduledTask -TaskName "shoponline-backup" -Action $backupAction -Trigger (New-BackupTrigger) `
        -Settings $backupSettings @account -Force | Out-Null
    Write-Host "Đã đăng ký shoponline-backup (mỗi 15 phút; giờ sao lưu đặt trên trang Sao lưu)"
}

if ($isNew["shoponline-restore"]) {
    # No trigger: the task only runs when the web asks for it.
    Register-ScheduledTask -TaskName "shoponline-restore" -Action $restoreAction `
        -Settings $restoreSettings @account -Force | Out-Null
    Write-Host "Đã đăng ký shoponline-restore (chạy khi admin bấm phục hồi trên web)"
}

if ($isNew["shoponline-retention"]) {
    Register-ScheduledTask -TaskName "shoponline-retention" -Action $retentionAction -Trigger (New-ScheduledTaskTrigger -Daily -At $RetentionTime) `
        -Settings $dailySettings @account -Force | Out-Null
    $retentionMode = if ($applyRetention) { "xóa thật" } else { "chỉ liệt kê vào data\logs\retention.log" }
    Write-Host "Đã đăng ký shoponline-retention (hằng ngày lúc $RetentionTime, $retentionMode)"
}

if ($OnlyMissing) { return }
Start-ScheduledTask -TaskName "shoponline-web"
Write-Host "Đã khởi động shoponline-web; mở http://<địa chỉ máy>:$WebPort"
