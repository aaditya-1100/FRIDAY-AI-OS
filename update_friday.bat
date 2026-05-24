@echo off
title FRIDAY Updater
color 0A
echo.
echo  ============================================
echo    FRIDAY AI - Update and Launch
echo  ============================================
echo.

echo [1/4] Stopping any running FRIDAY instance...
taskkill /F /IM FRIDAY.exe /T >nul 2>&1
taskkill /F /IM python.exe /T >nul 2>&1
timeout /t 2 /nobreak >nul

echo [2/4] Building updated frontend...
cd /d C:\FRIDAY\frontend
if exist dist rmdir /s /q dist
call npm run build
if %ERRORLEVEL% NEQ 0 ( echo BUILD FAILED & pause & exit /b 1 )

echo [3/4] Repacking app.asar...
set STAGING=C:\FRIDAY\frontend\dist-electron\_stg
set ASAR=C:\FRIDAY\frontend\dist-electron\win-unpacked\resources\app.asar
if exist "%STAGING%" rmdir /s /q "%STAGING%"
mkdir "%STAGING%\dist"
mkdir "%STAGING%\electron"
xcopy /E /I /Y "C:\FRIDAY\frontend\dist\*"       "%STAGING%\dist\" >nul
copy /Y "C:\FRIDAY\frontend\electron\main.cjs"    "%STAGING%\electron\main.cjs" >nul
echo { "name": "friday", "version": "1.0.0", "main": "electron/main.cjs" } > "%STAGING%\package.json"
if exist "%ASAR%" del /F /Q "%ASAR%"
call npx asar pack "%STAGING%" "%ASAR%"
rmdir /s /q "%STAGING%"

echo [4/4] Launching FRIDAY...
start "" "C:\FRIDAY\frontend\dist-electron\win-unpacked\FRIDAY.exe"
echo.
echo  FRIDAY updated and launched!
timeout /t 3 /nobreak >nul
exit
