param(
    [int]$MemoryGB = 8,
    [int]$Processors = 8,
    [int]$SwapGB = 4,
    [ValidateSet("disabled", "gradual", "dropCache")]
    [string]$AutoMemoryReclaim = "dropCache",
    [string]$Distro,
    [switch]$ShutdownAfter
)

$projectRoot = Split-Path -Parent $PSScriptRoot
$wslConfigPath = Join-Path $env:USERPROFILE ".wslconfig"
$backupPath = "$wslConfigPath.bak-$(Get-Date -Format yyyyMMdd-HHmmss)"

if (Test-Path $wslConfigPath) {
    Copy-Item -LiteralPath $wslConfigPath -Destination $backupPath -Force
}

$content = @"
[wsl2]
memory=${MemoryGB}GB
processors=$Processors
swap=${SwapGB}GB

[experimental]
autoMemoryReclaim=$AutoMemoryReclaim
"@

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($wslConfigPath, $content.Trim() + [Environment]::NewLine, $utf8NoBom)

Write-Output "Actualizado $wslConfigPath"
if (Test-Path $backupPath) {
    Write-Output "Backup: $backupPath"
}

$dropArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $PSScriptRoot "drop_wsl_cache.ps1"), "-Mode", "all", "-WaitSeconds", "3")
if ($Distro) {
    $dropArgs += @("-Distro", $Distro)
}
& powershell @dropArgs
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

if ($ShutdownAfter) {
    Write-Output "Aplicando reinicio de WSL para activar el limite de memoria."
    wsl --shutdown
    exit $LASTEXITCODE
}

Write-Output "Nota: el limite memory=${MemoryGB}GB y autoMemoryReclaim=$AutoMemoryReclaim se aplican al reiniciar WSL con 'wsl --shutdown'."
