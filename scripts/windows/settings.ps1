# Dot-sourced by the other scripts: read a setting from the environment, else the repo-root env file.
$script:RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path

function Get-Setting([string]$name, [string]$default = "") {
    $value = [Environment]::GetEnvironmentVariable($name)
    if (-not $value) {
        $envFile = Join-Path $script:RepoRoot ".env"
        if (Test-Path $envFile) {
            foreach ($line in Get-Content $envFile -Encoding UTF8) {
                if ($line -match "^\s*$([regex]::Escape($name))\s*=\s*(.*)$") {
                    $value = $Matches[1].Trim().Trim('"').Trim("'")
                }
            }
        }
    }
    if (-not $value) { $value = $default }
    return $value
}

function ConvertFrom-DatabaseUrl([string]$url) {
    if ($url -notmatch "^postgresql(\+\w+)?://([^:]+):([^@]*)@([^:/]+)(:(\d+))?/([^?]+)") {
        throw "Chuỗi kết nối không đúng dạng postgresql://user:password@host:port/db"
    }
    return @{
        User     = $Matches[2]
        Password = [uri]::UnescapeDataString($Matches[3])
        Host     = $Matches[4]
        Port     = if ($Matches[6]) { $Matches[6] } else { "5432" }
        Database = $Matches[7]
    }
}

# Windows Terminal, when it is the default console host, ignores pwsh -WindowStyle Hidden and
# opens a window for every interactive-logon task. conhost --headless runs the program with no
# window at all. The flag is undocumented and conhost does not pass the child's exit code on,
# so check it once per script run with a marker file.
$script:HeadlessConsole = $null

function Test-HeadlessConsole {
    if ($null -ne $script:HeadlessConsole) { return $script:HeadlessConsole }
    $marker = Join-Path ([IO.Path]::GetTempPath()) "shoponline-headless-$([guid]::NewGuid().ToString('N')).txt"
    $ok = $false
    try {
        Start-Process -FilePath (Join-Path $env:windir "System32\conhost.exe") -WindowStyle Hidden -Wait `
            -ArgumentList "--headless cmd.exe /c echo ok> `"$marker`""
        $ok = (Test-Path $marker) -and ((Get-Content $marker -Raw).Trim() -eq "ok")
    } catch {
        $ok = $false
    } finally {
        Remove-Item $marker -ErrorAction SilentlyContinue
    }
    $script:HeadlessConsole = $ok
    if (-not $ok) {
        Write-Warning "Máy này không chạy được conhost --headless; tác vụ chạy qua pwsh -WindowStyle Hidden và có thể hiện cửa sổ."
    }
    return $ok
}

# A task action that runs $Execute with no console window (see Test-HeadlessConsole).
function New-HiddenTaskAction([string]$Execute, [string]$Argument = "", [string]$WorkingDirectory) {
    if (Test-HeadlessConsole) {
        $exe = Join-Path $env:windir "System32\conhost.exe"
        $arg = "--headless `"$Execute`" $Argument".TrimEnd()
    } else {
        $exe = (Get-Command pwsh).Source
        if ([IO.Path]::GetFileNameWithoutExtension($Execute) -eq "pwsh") {
            $arg = "-WindowStyle Hidden $Argument".TrimEnd()
        } else {
            $inner = "& '$Execute' $Argument".TrimEnd()
            $arg = "-NoProfile -WindowStyle Hidden -Command `"$inner`""
        }
    }
    return New-ScheduledTaskAction -Execute $exe -Argument $arg -WorkingDirectory $WorkingDirectory
}

# Task settings that keep running on a laptop's battery; takes New-ScheduledTaskSettingsSet parameters.
function New-TaskSettings {
    New-ScheduledTaskSettingsSet @args -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
}

# True when an existing task already runs $action with the battery behaviour of $settings.
function Test-TaskMatches($task, $action, $settings) {
    $current = $task.Actions[0]
    return $task.Actions.Count -eq 1 -and
        $current.Execute -eq $action.Execute -and
        "$($current.Arguments)" -eq "$($action.Arguments)" -and
        $task.Settings.DisallowStartIfOnBatteries -eq $settings.DisallowStartIfOnBatteries -and
        $task.Settings.StopIfGoingOnBatteries -eq $settings.StopIfGoingOnBatteries
}
