$scriptPath = $PSScriptRoot
Set-Location -Path $scriptPath
$launcherPath = "launcher\start.py"

if (-not (Test-Path $launcherPath)) {
    Write-Host "Launcher not found. Downloading..." -ForegroundColor Yellow
    $url = "https://raw.githubusercontent.com/Ner-Kun/omni-trans-core/main/launcher/start.py"
    $launcherDir = "launcher"
    
    if (-not (Test-Path $launcherDir)) {
        New-Item -Path $launcherDir -ItemType Directory | Out-Null
    }
    
    try {
        Invoke-WebRequest -Uri $url -OutFile $launcherPath
        Write-Host "Launcher downloaded successfully." -ForegroundColor Green
    } catch {
        Write-Host "Failed to download launcher. Please check your internet connection." -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }
}

py -3 $launcherPath $args