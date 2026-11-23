<#
.SYNOPSIS
  Stop or start the web and the SAP robot of this checkout.

.DESCRIPTION
  Used by update-production.ps1 (dot-sourced) and by restore and migration (run with -Action).
    -Action stop    stop the robot, then the web, and wait until the web port is free
    -Action start   start the web and wait until the login page answers, then the robot
  Exit code 0 on success, 1 when something did not stop or start.
  Dot-source it without -Action to get the functions: Test-WebUp, Stop-Web, Start-Web,
  Get-RobotProcess, Stop-Robot, Start-Robot.

.EXAMPLE
  pwsh -File scripts\windows\service-control.ps1 -Action stop
#>
param(
    [ValidateSet("", "stop", "start")][string]$Action = "",
    [int]$WaitSeconds = 60
)

. (Join-Path $PSScriptRoot "settings.ps1")
$port = [int](Get-Setting "SHOPONLINE_WEB_PORT" "8750")
$webHost = Get-Setting "SHOPONLINE_WEB_HOST" "127.0.0.1"
if ($webHost -eq "0.0.0.0") { $webHost = "127.0.0.1" }
$loginUrl = "http://${webHost}:$port/login"
$robotPattern = 'shoponline(\.exe)?"?\s+robot(\s|$)'

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

# The robot always runs: it starts without SAP settings and reports on the web page "Kết nối SAP"
# what is missing. Returns $false when it exits right after being started.
function Start-Robot {
    if (Get-RobotProcess) { Write-Host "Robot đang chạy"; return $true }
    Start-ScheduledTask -TaskName "shoponline-robot"
    # A robot that cannot start (bad settings, a second robot) exits within seconds.
    Start-Sleep -Seconds 20
    if (Get-RobotProcess) { Write-Host "Đã khởi động robot"; return $true }
    $dataDir = Get-Setting "SHOPONLINE_DATA_DIR" (Join-Path $script:RepoRoot "data")
    Write-Warning "Robot dừng ngay sau khi khởi động; xem $(Join-Path $dataDir 'logs\robot.log') hoặc chạy tay: uv run --no-dev --extra robot shoponline robot"
    return $false
}

if ($Action) {
    $ErrorActionPreference = "Stop"
    try {
        if ($Action -eq "stop") {
            Stop-Robot
            Stop-Web
        } else {
            Start-Web
            if (-not (Start-Robot)) { throw "Robot không khởi động được" }
        }
    } catch {
        Write-Error $_
        exit 1
    }
    exit 0
}
