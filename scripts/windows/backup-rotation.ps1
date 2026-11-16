<#
.SYNOPSIS
  Which backups to keep in a folder: every backup of today, the newest backup of each earlier
  day for KeepDays days, nothing older. Dot-sourced by backup-db.ps1.

.DESCRIPTION
  The day comes from the file name (shoponline-<db>-yyyyMMdd-HHmmss.7z), not the file time, so
  a copied or restored folder rotates the same way. Today keeps every backup: the one taken
  before a deploy is the way back from that deploy's migration. Files with another name are
  never touched.

.EXAMPLE
  . .\scripts\windows\backup-rotation.ps1
  Remove-OldBackups -Folder D:\backup-test -Database shoponline -KeepDays 14 -WhatIf
#>

function Remove-OldBackups {
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [Parameter(Mandatory)][string]$Folder,
        [Parameter(Mandatory)][string]$Database,
        [Parameter(Mandatory)][int]$KeepDays,
        [datetime]$Today = (Get-Date).Date
    )
    $pattern = "^shoponline-$([regex]::Escape($Database))-(\d{8})-(\d{6})\.7z$"
    $oldest = $Today.Date.AddDays(-$KeepDays)
    $byDay = Get-ChildItem -LiteralPath $Folder -File -Filter "shoponline-$Database-*.7z" |
        Where-Object { $_.Name -match $pattern } |
        Group-Object { [regex]::Match($_.Name, $pattern).Groups[1].Value }
    foreach ($day in $byDay) {
        $date = [datetime]::ParseExact($day.Name, "yyyyMMdd", [Globalization.CultureInfo]::InvariantCulture)
        if ($date -ge $Today.Date) { continue }
        $keep = if ($date -ge $oldest) { 1 } else { 0 }
        # Names sort by time within a day, so the newest is last.
        $drop = $day.Group | Sort-Object Name | Select-Object -SkipLast $keep
        foreach ($file in $drop) {
            if ($PSCmdlet.ShouldProcess($file.FullName, "Xóa bản sao lưu")) {
                Remove-Item -LiteralPath $file.FullName
            }
        }
    }
}
