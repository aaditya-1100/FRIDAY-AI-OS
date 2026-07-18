@echo off
setlocal enabledelayedexpansion

echo ==================================================
echo             FRIDAY AI ASSISTANT LAUNCHER
echo ==================================================
echo.

echo [1/2] Terminating any stale FRIDAY processes...
taskkill /F /IM FRIDAY.exe /T >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| find "8001" ^| find "LISTENING" 2^>nul') do taskkill /F /PID %%a /T >nul 2>&1

REM Detect release folder vs dev folder
if exist "%~dp0FRIDAY\FRIDAY.exe" (
    set "EXE_PATH=%~dp0FRIDAY\FRIDAY.exe"
) else (
    set "EXE_PATH=%~dp0frontend\dist-electron\FRIDAY-win32-x64\FRIDAY.exe"
)

if not exist "!EXE_PATH!" (
    echo [ERROR] FRIDAY.exe not found at: !EXE_PATH!
    echo Please run update_friday.bat first to build the application.
    pause
    exit /b 1
)

echo.
echo [2/2] Launching FRIDAY from: !EXE_PATH!
start "" "!EXE_PATH!"

echo.
echo FRIDAY is now running.
timeout /t 2 >nul
exit
