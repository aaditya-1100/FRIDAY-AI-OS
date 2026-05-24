@echo off
setlocal enabledelayedexpansion

echo ==================================================
echo             FRIDAY AI ASSISTANT LAUNCHER
echo ==================================================
echo.

echo [1/3] Terminating any stale FRIDAY processes...
taskkill /F /IM FRIDAY.exe /T >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| find "8001" ^| find "LISTENING"') do taskkill /F /PID %%a /T >nul 2>&1

set "EXE_PATH=%~dp0frontend\dist-electron\FRIDAY-win32-x64\FRIDAY.exe"

if not exist "!EXE_PATH!" (
    echo.
    echo [2/3] Executable not found. Compiling application codebase (first-time setup)...
    cd /d "%~dp0frontend"
    call npm run build:dir
    if !ERRORLEVEL! neq 0 (
        echo.
        echo [ERROR] Application failed to compile.
        pause
        exit /b 1
    )
    cd /d "%~dp0"
) else (
    echo.
    echo [2/3] Latest compiled executable found. Skipping build step for instant launch.
    echo (To force a full recompile, run: cd frontend ^&^& npm run build:dir)
)

echo.
echo [3/3] Launching FRIDAY...
start "" "!EXE_PATH!"

echo.
echo FRIDAY is now running.
timeout /t 2 >nul
exit
