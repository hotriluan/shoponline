<#
.SYNOPSIS
  Turn a clean Windows 10/11 64-bit machine into the shoponline production machine.

.DESCRIPTION
  Run from a normal (not elevated) Windows PowerShell under the Windows account that will run
  everything; that account should log on automatically. Every step checks whether it is
  already done, so the script can be rerun at any time; it only stops for what must be typed.

  Stage 1 (Windows PowerShell 5.1 is enough): installs Git, PowerShell 7, 7-Zip, GitHub CLI,
  PostgreSQL 16 and uv with winget, then clones the repo to C:\shoponline (or fast-forwards a
  clean checkout) and runs the repo's copy of this script under pwsh with -Stage2.

  Stage 2 (pwsh, inside the repo): uv sync; database and .env (create-databases.ps1); the
  missing .env lines (web address, backup folders, backup password); access rights on .env
  and the data folder; copy of an old data folder (-DataSource); restore of a backup into an
  empty database (-Archive); migrate; hidden Task Scheduler tasks; firewall rule and power
  settings (one UAC prompt); the deploy runner (not with -Prepare); start web and robot.
  It ends with a checklist of what is done and what is still manual.

  With -Prepare the machine is built before the move day: no deploy runner, and the robot
  task stays disabled because the robot on the old machine still uses the SAP user.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File setup.ps1 -Prepare -Archive D:\backup\shoponline-shoponline-20261120-230000.7z -DataSource \\share\shoponline-migrate\data

.EXAMPLE
  pwsh -ExecutionPolicy Bypass -File C:\shoponline\scripts\windows\setup-production-machine.ps1
#>
param(
    [string]$Archive,
    [string]$DataSource,
    [string]$DataDir = "C:\shoponline-data",
    [string]$RepoUrl = "https://github.com/hotriluan/shoponline.git",
    [switch]$Prepare,
    [switch]$Stage2
)

# Keep this file parseable by Windows PowerShell 5.1 (stage 1 runs there): no ??, no ternary,
# no && or ||, and keep the UTF-8 BOM so 5.1 reads the Vietnamese text as UTF-8.
$ErrorActionPreference = "Stop"
$RepoDir = "C:\shoponline"
$PgBin = "C:\Program Files\PostgreSQL\16\bin"
$SevenZip = "C:\Program Files\7-Zip\7z.exe"
$Me = "$env:USERDOMAIN\$env:USERNAME"

function Write-Step([string]$text) { Write-Host ""; Write-Host "== $text" -ForegroundColor Cyan }

function Update-SessionPath {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user"
}

function Assert-Native([string]$what) {
    if ($LASTEXITCODE -ne 0) { throw "$what lỗi (mã $LASTEXITCODE)" }
}

# ---------------------------------------------------------------- stage 1: software and code
if (-not $Stage2) {
    Write-Step "Kiểm tra máy"
    if (-not [Environment]::Is64BitOperatingSystem) { throw "Cần Windows 64-bit." }
    $identity = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
    if ($identity.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Đang chạy với quyền quản trị (Run as administrator). Mở PowerShell thường dưới tài khoản chạy hệ thống rồi chạy lại; script tự hỏi UAC khi cần."
    }
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "Không thấy winget. Cài 'App Installer' từ Microsoft Store (Windows 10 1809 trở lên), hoặc cài tay theo phụ lục trong docs/deployment-guide.md."
    }
    Write-Host "Tài khoản: $Me"

    Write-Step "Cài phần mềm (winget)"
    $packages = @(
        @{ Id = "Git.Git"; Args = @() },
        @{ Id = "Microsoft.PowerShell"; Args = @() },
        @{ Id = "7zip.7zip"; Args = @() },
        @{ Id = "GitHub.cli"; Args = @() },
        # --interactive: the PostgreSQL installer asks for the postgres superuser password.
        @{ Id = "PostgreSQL.PostgreSQL.16"; Args = @("--interactive") },
        @{ Id = "astral-sh.uv"; Args = @() }
    )
    foreach ($package in $packages) {
        $null = winget list --exact --id $package.Id --accept-source-agreements
        if ($LASTEXITCODE -eq 0) { Write-Host "Đã có $($package.Id)"; continue }
        if ($package.Id -like "PostgreSQL*") {
            Write-Host "Bộ cài PostgreSQL sẽ hỏi mật khẩu superuser 'postgres'. Ghi nhớ mật khẩu này: bước tạo database cần nó." -ForegroundColor Yellow
        }
        Write-Host "Cài $($package.Id)..."
        $installArgs = @("install", "--exact", "--id", $package.Id, "--accept-package-agreements", "--accept-source-agreements") + $package.Args
        & winget @installArgs
        if ($LASTEXITCODE -ne 0) {
            throw "Cài $($package.Id) lỗi (mã $LASTEXITCODE). Cài tay gói này rồi chạy lại script."
        }
    }
    Update-SessionPath
    foreach ($path in @((Join-Path $PgBin "psql.exe"), $SevenZip)) {
        if (-not (Test-Path $path)) { throw "Không thấy $path. Cài lại vào thư mục mặc định rồi chạy lại script." }
    }
    foreach ($command in @("git", "pwsh", "gh", "uv")) {
        if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
            throw "Không thấy lệnh $command sau khi cài. Mở cửa sổ PowerShell mới rồi chạy lại script."
        }
    }

    Write-Step "Mã nguồn $RepoDir"
    if (Test-Path (Join-Path $RepoDir ".git")) {
        $dirty = git -C $RepoDir status --porcelain --untracked-files=no
        Assert-Native "git status"
        if ($dirty) { throw "$RepoDir có sửa đổi cục bộ. Máy chạy thật chỉ nhận mã qua GitHub; bỏ các sửa đổi đó rồi chạy lại." }
        git -C $RepoDir fetch --quiet origin main; Assert-Native "git fetch"
        git -C $RepoDir merge --ff-only --quiet origin/main; Assert-Native "git merge"
        Write-Host "Đã có, cập nhật tới origin/main"
    } else {
        git clone $RepoUrl $RepoDir; Assert-Native "git clone"
    }

    $stage2Args = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $RepoDir "scripts\windows\setup-production-machine.ps1"), "-Stage2", "-DataDir", $DataDir)
    if ($Archive) { $stage2Args += @("-Archive", $Archive) }
    if ($DataSource) { $stage2Args += @("-DataSource", $DataSource) }
    if ($Prepare) { $stage2Args += "-Prepare" }
    & pwsh @stage2Args
    exit $LASTEXITCODE
}

# ---------------------------------------------------------------- stage 2: system (pwsh, in the repo)
. (Join-Path $PSScriptRoot "settings.ps1")
Set-Location $script:RepoRoot
$EnvFile = Join-Path $script:RepoRoot ".env"
$checks = [System.Collections.Generic.List[object]]::new()
function Add-Check([bool]$done, [string]$text, [string]$todo = "") {
    $checks.Add([pscustomobject]@{ Done = $done; Text = $text; Todo = $todo })
}

function Test-EnvLine([string]$name) {
    (Test-Path $EnvFile) -and [bool](Select-String -Path $EnvFile -Pattern "^\s*$([regex]::Escape($name))\s*=" -Quiet)
}

function Set-EnvLine([string]$name, [string]$value) {
    $lines = @(Get-Content $EnvFile -Encoding UTF8 | Where-Object { $_ -notmatch "^\s*$([regex]::Escape($name))\s*=" })
    $lines += "$name=$value"
    [IO.File]::WriteAllLines($EnvFile, [string[]]$lines, [Text.UTF8Encoding]::new($false))
}

function Read-Secret([string]$prompt) {
    $secure = Read-Host -Prompt $prompt -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
}

Write-Step "Cách chạy ẩn"
$headless = Test-HeadlessConsole
if ($headless) { Write-Host "Tác vụ sẽ chạy ẩn (conhost --headless)" }
Add-Check $headless "Tác vụ chạy ẩn" "Máy không chạy được conhost --headless; tác vụ vẫn chạy nhưng có thể hiện cửa sổ."

Write-Step "Thư viện Python"
uv sync --frozen --no-dev --extra robot; Assert-Native "uv sync"

Write-Step "Database và .env"
$envCreated = $false
if (Test-Path $EnvFile) {
    Write-Host "Đã có $EnvFile, bỏ qua tạo database"
} else {
    & (Join-Path $PSScriptRoot "create-databases.ps1") -Environment prod -WriteEnvFile -DataDir $DataDir
    if (-not (Test-Path $EnvFile)) { throw "create-databases.ps1 không tạo $EnvFile" }
    $envCreated = $true
}

# create-databases.ps1 writes 127.0.0.1; a production machine serves the office network.
if ($envCreated -or -not (Test-EnvLine "SHOPONLINE_WEB_HOST")) {
    $lan = Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -and $_.IPv4Address } |
        Select-Object -First 1 | ForEach-Object { $_.IPv4Address[0].IPAddress }
    $answer = Read-Host "Địa chỉ IP để mở web trong mạng nội bộ [$lan]"
    if (-not $answer) { $answer = $lan }
    if (-not $answer) { throw "Cần một địa chỉ IP cho SHOPONLINE_WEB_HOST" }
    Set-EnvLine "SHOPONLINE_WEB_HOST" $answer
}
if (-not (Test-EnvLine "SHOPONLINE_BACKUP_DIRS")) {
    do { $dirs = Read-Host "Thư mục sao lưu, ngăn cách bằng ';' (giống máy cũ)" } while (-not $dirs.Trim())
    Set-EnvLine "SHOPONLINE_BACKUP_DIRS" $dirs.Trim()
}
if (-not (Test-EnvLine "SHOPONLINE_BACKUP_PASSWORD")) {
    while ($true) {
        $backupPassword = Read-Secret "Mật khẩu sao lưu (giống máy cũ, để mở được bản sao lưu)"
        if ($backupPassword -and $backupPassword -eq (Read-Secret "Nhập lại mật khẩu sao lưu")) { break }
        Write-Warning "Trống hoặc hai lần nhập không khớp; nhập lại."
    }
    Set-EnvLine "SHOPONLINE_BACKUP_PASSWORD" $backupPassword
    $backupPassword = $null
}
$DataDir = Get-Setting "SHOPONLINE_DATA_DIR" $DataDir
$port = [int](Get-Setting "SHOPONLINE_WEB_PORT" "8750")
$webHost = Get-Setting "SHOPONLINE_WEB_HOST" "127.0.0.1"
Add-Check ($webHost -ne "127.0.0.1") "Web mở trong mạng nội bộ (${webHost}:$port)" "SHOPONLINE_WEB_HOST là 127.0.0.1: chỉ máy này mở được web. Sửa dòng đó trong $EnvFile rồi chạy lại."

Write-Step "Quyền truy cập .env và $DataDir"
New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
icacls $EnvFile /inheritance:r /grant:r "${Me}:F" "*S-1-5-32-544:F" "*S-1-5-18:F" | Out-Null
Assert-Native "icacls .env"
icacls $DataDir /inheritance:r /grant:r "${Me}:(OI)(CI)F" "*S-1-5-32-544:(OI)(CI)F" "*S-1-5-18:(OI)(CI)F" | Out-Null
Assert-Native "icacls $DataDir"
Write-Host "Chỉ $Me, Administrators và SYSTEM đọc được"

if ($DataSource) {
    Write-Step "Chép thư mục dữ liệu từ $DataSource"
    robocopy $DataSource $DataDir /E /COPY:DAT /R:2 /W:5 /NP /NFL /NDL
    if ($LASTEXITCODE -ge 8) { throw "robocopy lỗi (mã $LASTEXITCODE)" }
    $global:LASTEXITCODE = 0
}

Write-Step "Khôi phục bản sao lưu"
$db = ConvertFrom-DatabaseUrl (Get-Setting "SHOPONLINE_DATABASE_URL")
$env:PGPASSWORD = $db.Password
try {
    $tables = & (Join-Path $PgBin "psql.exe") -h $db.Host -p $db.Port -U $db.User -d $db.Database -tAc `
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'"
    Assert-Native "psql"
} finally {
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
}
$restoreCommand = "pwsh -File scripts\windows\restore-db.ps1 -Archive <file .7z> -TargetSetting SHOPONLINE_DATABASE_URL -AllowProduction"
if (-not $Archive) {
    Write-Host "Không có -Archive, bỏ qua"
} elseif ([int]$tables -gt 0) {
    Write-Host "Database $($db.Database) đã có dữ liệu, không khôi phục đè. Muốn ghi đè thì dừng web rồi chạy tay: $restoreCommand"
} else {
    & pwsh -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "restore-db.ps1") `
        -Archive $Archive -TargetSetting SHOPONLINE_DATABASE_URL -AllowProduction
    Assert-Native "Khôi phục"
    Write-Host "Đã khôi phục $Archive"
}

Write-Step "Schema"
uv run --no-dev shoponline migrate; Assert-Native "migrate"

Write-Step "Tác vụ Task Scheduler"
$register = Join-Path $PSScriptRoot "register-tasks.ps1"
& pwsh -NoProfile -ExecutionPolicy Bypass -File $register -User $Me -AtLogOn -OnlyMissing -WebPort $port
Assert-Native "Đăng ký tác vụ"
& pwsh -NoProfile -ExecutionPolicy Bypass -File $register -RobotUser $Me -OnlyMissing
Assert-Native "Đăng ký tác vụ robot"

Write-Step "Tường lửa và nguồn điện"
# True when the plugged-in timeout is "never". The label is English-only; on another display
# language this reads as not done and the (harmless) elevated block runs again.
function Test-PowerOff([string]$group, [string]$setting) {
    $out = powercfg /query SCHEME_CURRENT $group $setting
    return [bool]($out | Select-String -Pattern "AC Power Setting Index:\s*0x0+\s*$" -Quiet)
}
$firewall = [bool](Get-NetFirewallRule -DisplayName "shoponline-web" -ErrorAction SilentlyContinue)
$powerDone = (Test-PowerOff SUB_SLEEP STANDBYIDLE) -and (Test-PowerOff SUB_SLEEP HIBERNATEIDLE) -and (Test-PowerOff SUB_VIDEO VIDEOIDLE)
if ($firewall -and $powerDone) {
    Write-Host "Đã có quy tắc tường lửa và máy không tự ngủ"
} else {
    Write-Host "Windows sẽ hỏi quyền quản trị (UAC) một lần"
    $elevated = @"
`$ErrorActionPreference = 'Stop'
if (-not (Get-NetFirewallRule -DisplayName 'shoponline-web' -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName 'shoponline-web' -Direction Inbound -Protocol TCP -LocalPort $port -Action Allow -Profile Domain,Private | Out-Null
}
powercfg /change standby-timeout-ac 0
powercfg /change monitor-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
"@
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($elevated))
    $process = Start-Process (Get-Command pwsh).Source -Verb RunAs -Wait -PassThru -ArgumentList "-NoProfile -EncodedCommand $encoded"
    if ($process.ExitCode -ne 0) { throw "Khối lệnh quản trị lỗi (mã $($process.ExitCode))" }
    $firewall = [bool](Get-NetFirewallRule -DisplayName "shoponline-web" -ErrorAction SilentlyContinue)
}
Add-Check $firewall "Tường lửa mở cổng $port cho mạng Domain và Private" "Chạy lại script và chấp nhận UAC."

if ($Prepare) {
    Add-Check $false "Runner deploy" "Cài vào ngày chuyển máy: chạy lại script không có -Prepare (docs/deployment-guide.md, mục Chuyển máy chạy thật)."
} else {
    Write-Step "Runner deploy"
    gh auth status 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { gh auth login; Assert-Native "gh auth login" }
    & pwsh -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "install-deploy-runner.ps1")
    Assert-Native "Cài runner"
    Add-Check $true "Runner deploy shoponline-prod đã đăng ký"
}

Write-Step "Bật web và robot"
$loginHost = $webHost
if ($loginHost -eq "0.0.0.0") { $loginHost = "127.0.0.1" }
$loginUrl = "http://${loginHost}:$port/login"
function Test-WebUp {
    try { return (Invoke-WebRequest $loginUrl -UseBasicParsing -TimeoutSec 5).StatusCode -eq 200 }
    catch { return $false }
}
if (-not (Test-WebUp)) {
    Start-ScheduledTask -TaskName "shoponline-web"
    $deadline = (Get-Date).AddSeconds(60)
    while (-not (Test-WebUp) -and (Get-Date) -lt $deadline) { Start-Sleep -Seconds 2 }
}
$webUp = Test-WebUp
Add-Check $webUp "Web trả lời $loginUrl" "Xem Task Scheduler → shoponline-web và $DataDir\logs\web.log."

if ($Prepare) {
    Stop-ScheduledTask -TaskName "shoponline-robot" -ErrorAction SilentlyContinue
    Disable-ScheduledTask -TaskName "shoponline-robot" | Out-Null
    Add-Check $true "Robot để Disabled (robot trên máy cũ vẫn dùng user SAP)"
} else {
    Enable-ScheduledTask -TaskName "shoponline-robot" | Out-Null
    if ((Get-ScheduledTask -TaskName "shoponline-robot").State -ne "Running") { Start-ScheduledTask -TaskName "shoponline-robot" }
    Add-Check $true "Robot đã bật"
}

# ---------------------------------------------------------------- checklist
$saplogon = Get-Setting "SHOPONLINE_SAPLOGON_PATH" "C:\Program Files (x86)\SAP\FrontEnd\SAPgui\saplogon.exe"
Add-Check (Test-Path $saplogon) "SAP GUI đã cài ($saplogon)" "Cài SAP GUI cùng phiên bản máy cũ, bật scripting phía máy khách, tạo mục SAP Logon trỏ AEP (docs/robot-machine-setup.md mục 2)."
Add-Check $false "SAP GUI scripting phía máy khách" "SAP GUI Options → Accessibility & Scripting: bật scripting, bỏ hai ô Notify (docs/robot-machine-setup.md mục 2)."
$excel = Test-Path "Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\excel.exe"
Add-Check $excel "Microsoft Excel đã cài" "Cài Microsoft Excel (docs/robot-machine-setup.md mục 2)."
$winlogon = Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" -ErrorAction SilentlyContinue
$autologon = $winlogon -and $winlogon.AutoAdminLogon -eq "1" -and $winlogon.DefaultUserName -eq $env:USERNAME
Add-Check $autologon "Tự đăng nhập $Me" "Chạy Sysinternals Autologon cho tài khoản này (docs/robot-machine-setup.md mục 1)."
Add-Check $false "Khóa màn hình và trình bảo vệ màn hình" "Tắt cả hai cho tài khoản này; đặt độ phân giải cố định (docs/robot-machine-setup.md mục 1)."
$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$sapStatus = uv run --no-dev --extra robot shoponline sap-password status 2>$null
Add-Check ("$sapStatus" -match "đã có") "Mật khẩu SAP của robot trên máy này" "uv run --extra robot shoponline sap-password set"
Add-Check $false "Kiểm tra kết nối SAP" "Mở trang Robot SAP → Kết nối SAP và bấm Kiểm tra (sau khi robot cũ đã tắt)."

Write-Host ""
Write-Host "================ Bảng kiểm tra ================" -ForegroundColor Cyan
foreach ($check in $checks) {
    if ($check.Done) {
        Write-Host "  [x] $($check.Text)" -ForegroundColor Green
    } else {
        Write-Host "  [ ] $($check.Text)" -ForegroundColor Yellow
        Write-Host "      Việc tay: $($check.Todo)"
    }
}
