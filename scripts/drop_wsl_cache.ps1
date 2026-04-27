param(
    [string]$Distro,
    [ValidateSet("all", "pagecache", "dentries")]
    [string]$Mode = "all",
    [double]$WaitSeconds = 2
)

$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot

try {
    $pythonCommand = if (Get-Command python -ErrorAction SilentlyContinue) { "python" } else { "py" }
    $args = @("-m", "wsl_memory_doctor", "drop-cache", "--mode", $Mode, "--wait-seconds", "$WaitSeconds")
    if ($Distro) {
        $args += @("--distro", $Distro)
    }
    & $pythonCommand @args
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
