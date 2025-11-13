Write-Host "Starting Omni Trans Launcher..." -ForegroundColor Cyan
$scriptPath = $PSScriptRoot
Set-Location -Path $scriptPath
py -3 launcher\start.py $args