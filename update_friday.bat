@echo off
title FRIDAY Updater
color 0A

echo.
echo  ============================================
echo    FRIDAY AI - Update and Launch
echo  ============================================
echo.

:: Step 1 - Kill any running FRIDAY instance
echo [1/4] Stopping any running FRIDAY instance...
taskkill /F /IM FRIDAY.exe /T >nul 2>&1
taskkill /F /IM electron.exe /T >nul 2>&1
taskkill /F /IM python.exe /T >nul 2>&1
timeout /t 2 /nobreak >nul
echo       Done.

:: Step 2 - Build the frontend
echo.
echo [2/4] Building updated frontend...
cd /d C:\FRIDAY\frontend
call npm run build
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo  ERROR: Frontend build failed. Check errors above.
    pause
    exit /b 1
)
echo       Done.

:: Step 3 - Package into .exe
echo.
echo [3/4] Packaging into FRIDAY.exe...
call npx electron-builder --win --dir
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo  WARNING: Packaging had issues but continuing...
)
echo       Done.

:: Step 4 - Launch the updated app
echo.
echo [4/4] Launching updated FRIDAY...
start "" "C:\FRIDAY\frontend\dist-electron\win-unpacked\FRIDAY.exe"

echo.
echo  ============================================
echo    FRIDAY updated and launched successfully!
echo  ============================================
echo.
timeout /t 3 /nobreak >nul
exit
