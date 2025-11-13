@echo off
chcp 65001 > nul
cd /d "%~dp0"
where wt.exe >nul 2>nul
if %errorlevel% equ 0 (
    echo Found Windows Terminal. Launching in a new, modern window...
    wt.exe --title "Omni Trans Launcher" powershell.exe -ExecutionPolicy Bypass -File "%~dp0run.ps1" %*
    goto :eof
)

echo Windows Terminal not found. Launching in the legacy console.
echo (For the best visual experience, consider installing 'Windows Terminal' from the Microsoft Store)

powershell.exe -ExecutionPolicy Bypass -File ".\run.ps1" %*

pause

:eof