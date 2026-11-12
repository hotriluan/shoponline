<#
.SYNOPSIS
  Register the Task Scheduler jobs on the production machine: web at startup, daily backup.

.DESCRIPTION
  Run from an elevated PowerShell 7 on the production machine, inside the repo folder.
  Tasks run as -User (the account that owns the repo, env file and data folder).
  Refuses to register when something already listens on the web port, so no second web
  process is started next to a stale one.

  With -RobotUser it registers only the SAP robot task instead: it starts when that account
  logs on (the robot needs the account's desktop for SAP GUI) and never runs twice at once.
  Run it after the robot machine is set up as in docs/robot-machine-setup.md.

.EXAMPLE
  pwsh -ExecutionPolicy Bypass -File scripts\windows\register-tasks.ps1 -User MAYCHU\shoponline -BackupTime 23:00

.EXAMPLE
  pwsh -ExecutionPolicy Bypass -File scripts\windows\register-tasks.ps1 -RobotUser MAYCHU\saprobot
#>
param(
    [string]$User,
    [string]$RobotUser,
    [string]$BackupTime = "23:00",
    [int]$WebPort = 8750,
    [string]$Uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if (-not $Uv) { throw "Không thấy uv; truyền -Uv <đường dẫn uv.exe>" }

if ($RobotUser) {
    $running = Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'uv.exe'" |
        Where-Object { $_.CommandLine -match 'shoponline(\.exe)?"?\s+robot(\s|$)' }
    if ($running) {
        throw "Robot đang chạy (PID $($running.ProcessId -join ', ')). Dừng nó trước khi đăng ký lại."
    }
    $robotAction = New-ScheduledTaskAction -Execute $Uv -Argument "run shoponline robot" -WorkingDirectory $repoRoot
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

$listening = Get-NetTCPConnection -LocalPort $WebPort -State Listen -ErrorAction SilentlyContinue
if ($listening) {
    $owner = Get-Process -Id $listening[0].OwningProcess -ErrorAction SilentlyContinue
    throw "Cổng $WebPort đang được $($owner.ProcessName) (PID $($listening[0].OwningProcess)) dùng. Dừng tiến trình đó hoặc đổi SHOPONLINE_WEB_PORT trước."
}

$secure = Read-Host -Prompt "Mật khẩu Windows của $User" -AsSecureString
$plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)

$webAction = New-ScheduledTaskAction -Execute $Uv -Argument "run shoponline web" -WorkingDirectory $repoRoot
Register-ScheduledTask -TaskName "shoponline-web" -Action $webAction -Trigger (New-ScheduledTaskTrigger -AtStartup) `
    -Settings $settings -User $User -Password $plain -RunLevel Limited -Force | Out-Null
Write-Host "Đã đăng ký shoponline-web (chạy khi máy khởi động)"

$pwsh = (Get-Command pwsh).Source
$backupAction = New-ScheduledTaskAction -Execute $pwsh `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$repoRoot\scripts\windows\backup-db.ps1`"" -WorkingDirectory $repoRoot
$backupSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1)
Register-ScheduledTask -TaskName "shoponline-backup" -Action $backupAction -Trigger (New-ScheduledTaskTrigger -Daily -At $BackupTime) `
    -Settings $backupSettings -User $User -Password $plain -RunLevel Limited -Force | Out-Null
Write-Host "Đã đăng ký shoponline-backup (hằng ngày lúc $BackupTime)"

Start-ScheduledTask -TaskName "shoponline-web"
Write-Host "Đã khởi động shoponline-web; mở http://<địa chỉ máy>:$WebPort"
