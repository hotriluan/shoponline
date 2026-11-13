<#
.SYNOPSIS
  Register the Task Scheduler jobs on the production machine: web at startup, daily backup,
  daily data retention (list-only unless -RetentionApply).

.DESCRIPTION
  Run from an elevated PowerShell 7 on the production machine, inside the repo folder.
  Tasks run as -User (the account that owns the repo, env file and data folder).
  Refuses to register when something already listens on the web port, so no second web
  process is started next to a stale one.

  With -RobotUser it registers only the SAP robot task instead: it starts when that account
  logs on (the robot needs the account's desktop for SAP GUI) and never runs twice at once.
  Run it after the robot machine is set up as in docs/robot-machine-setup.md.

  With -OnlyMissing it registers only the tasks that do not exist yet, leaves existing ones
  (and the options chosen for them, such as -RetentionApply) untouched, and starts nothing.
  update-production.ps1 calls it this way on every deploy.

.EXAMPLE
  pwsh -ExecutionPolicy Bypass -File scripts\windows\register-tasks.ps1 -User MAYCHU\shoponline -BackupTime 23:00

.EXAMPLE
  pwsh -ExecutionPolicy Bypass -File scripts\windows\register-tasks.ps1 -User $env:USERDOMAIN\$env:USERNAME -AtLogOn

.EXAMPLE
  pwsh -ExecutionPolicy Bypass -File scripts\windows\register-tasks.ps1 -RobotUser MAYCHU\saprobot
#>
param(
    [string]$User,
    [string]$RobotUser,
    [string]$BackupTime = "23:00",
    # Run web and backup in -User's session when that user logs on (no stored password, no
    # admin rights needed when -User is the current user). For a machine one person logs on to.
    [switch]$AtLogOn,
    # The daily retention task only lists what is past SHOPONLINE_RETENTION_DAYS until this is
    # passed; turn it on after someone has reviewed a week of data\logs\retention.log.
    [switch]$RetentionApply,
    [string]$RetentionTime = "23:30",
    [switch]$OnlyMissing,
    [int]$WebPort = 8750,
    [string]$Uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if (-not $Uv) { throw "Không thấy uv; truyền -Uv <đường dẫn uv.exe>" }
# Hidden pwsh wrapper: an interactive-logon task would otherwise open a console window someone could close.
$pwsh = (Get-Command pwsh).Source

function Test-TaskWanted([string]$name) {
    if (-not $OnlyMissing) { return $true }
    if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) {
        Write-Host "Đã có $name, giữ nguyên"
        return $false
    }
    return $true
}

if ($RobotUser) {
    if (-not (Test-TaskWanted "shoponline-robot")) { return }
    $running = Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'uv.exe'" |
        Where-Object { $_.CommandLine -match 'shoponline(\.exe)?"?\s+robot(\s|$)' }
    if ($running) {
        throw "Robot đang chạy (PID $($running.ProcessId -join ', ')). Dừng nó trước khi đăng ký lại."
    }
    $robotAction = New-ScheduledTaskAction -Execute $pwsh `
        -Argument "-NoProfile -WindowStyle Hidden -Command `"& '$Uv' run --no-dev --extra robot shoponline robot`"" -WorkingDirectory $repoRoot
    $robotPrincipal = New-ScheduledTaskPrincipal -UserId $RobotUser -LogonType Interactive -RunLevel Limited
    $robotSettings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -RestartCount 3 `
        -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
    Register-ScheduledTask -TaskName "shoponline-robot" -Action $robotAction `
        -Trigger (New-ScheduledTaskTrigger -AtLogOn -User $RobotUser) -Principal $robotPrincipal `
        -Settings $robotSettings -Force | Out-Null
    Write-Host "Đã đăng ký shoponline-robot (chạy khi $RobotUser đăng nhập)"
    return
}
if (-not $User) { throw "Truyền -User (web và sao lưu) hoặc -RobotUser (robot SAP)" }
if ($OnlyMissing -and -not $AtLogOn) { throw "-OnlyMissing chỉ dùng cùng -AtLogOn (không hỏi mật khẩu)" }

$wantWeb = Test-TaskWanted "shoponline-web"
$wantBackup = Test-TaskWanted "shoponline-backup"
$wantRetention = Test-TaskWanted "shoponline-retention"
if (-not ($wantWeb -or $wantBackup -or $wantRetention)) { return }

$listening = Get-NetTCPConnection -LocalPort $WebPort -State Listen -ErrorAction SilentlyContinue
if ($listening -and $wantWeb) {
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
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
$dailySettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1)

if ($wantWeb) {
    $webAction = New-ScheduledTaskAction -Execute $pwsh `
        -Argument "-NoProfile -WindowStyle Hidden -Command `"& '$Uv' run --no-dev shoponline web`"" -WorkingDirectory $repoRoot
    Register-ScheduledTask -TaskName "shoponline-web" -Action $webAction -Trigger $webTrigger `
        -Settings $settings @account -Force | Out-Null
    Write-Host "Đã đăng ký shoponline-web (chạy $webWhen)"
}

if ($wantBackup) {
    $backupAction = New-ScheduledTaskAction -Execute $pwsh `
        -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$repoRoot\scripts\windows\backup-db.ps1`"" -WorkingDirectory $repoRoot
    Register-ScheduledTask -TaskName "shoponline-backup" -Action $backupAction -Trigger (New-ScheduledTaskTrigger -Daily -At $BackupTime) `
        -Settings $dailySettings @account -Force | Out-Null
    Write-Host "Đã đăng ký shoponline-backup (hằng ngày lúc $BackupTime)"
}

if ($wantRetention) {
    $retentionArgs = if ($RetentionApply) { "retention --apply" } else { "retention" }
    $retentionAction = New-ScheduledTaskAction -Execute $pwsh `
        -Argument "-NoProfile -WindowStyle Hidden -Command `"& '$Uv' run --no-dev shoponline $retentionArgs`"" -WorkingDirectory $repoRoot
    Register-ScheduledTask -TaskName "shoponline-retention" -Action $retentionAction -Trigger (New-ScheduledTaskTrigger -Daily -At $RetentionTime) `
        -Settings $dailySettings @account -Force | Out-Null
    $retentionMode = if ($RetentionApply) { "xóa thật" } else { "chỉ liệt kê vào data\logs\retention.log" }
    Write-Host "Đã đăng ký shoponline-retention (hằng ngày lúc $RetentionTime, $retentionMode)"
}

if ($OnlyMissing) { return }
Start-ScheduledTask -TaskName "shoponline-web"
Write-Host "Đã khởi động shoponline-web; mở http://<địa chỉ máy>:$WebPort"
