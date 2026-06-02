@echo off
setlocal enabledelayedexpansion

echo ==================================================
echo             FRIDAY AI ASSISTANT LAUNCHER
echo ==================================================
echo.

echo [1/3] Terminating any stale FRIDAY processes...
taskkill /F /IM FRIDAY.exe /T >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| find "8001" ^| find "LISTENING" 2^>nul') do taskkill /F /PID %%a /T >nul 2>&1

REM electron-packager produces: dist-electron\FRIDAY-win32-x64\FRIDAY.exe
set "EXE_PATH=%~dp0frontend\dist-electron\FRIDAY-win32-x64\FRIDAY.exe"

echo [2/3] Checking if build is up-to-date...
if not exist "!EXE_PATH!" (
    echo [INFO] FRIDAY.exe not found. Running a fresh build...
    cd /d "%~dp0"
    call update_friday.bat
    if !ERRORLEVEL! neq 0 (
        echo.
        echo [ERROR] Build failed. Check errors above.
        pause
        exit /b 1
    )
)

if not exist "!EXE_PATH!" (
    echo [ERROR] FRIDAY.exe still not found after build. Packaging failed.
    pause
    exit /b 1
)

echo.
echo [3/3] Launching FRIDAY from: !EXE_PATH!
start "" "!EXE_PATH!"

echo.
echo FRIDAY is now running.
timeout /t 2 >nul
exit
