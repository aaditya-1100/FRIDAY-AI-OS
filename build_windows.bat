@echo off
echo ==================================================
echo             FRIDAY AI BUILD MANAGER
echo ==================================================
echo.

echo [1/3] Cleaning up stale build assets...
taskkill /F /IM FRIDAY.exe /T >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| find "8001" ^| find "LISTENING"') do taskkill /F /PID %%a /T >nul 2>&1

if exist backend\build rmdir /s /q backend\build
if exist backend\dist rmdir /s /q backend\dist
if exist frontend\dist rmdir /s /q frontend\dist
if exist frontend\dist-electron rmdir /s /q frontend\dist-electron
echo Stale assets cleaned.

echo.
echo [2/3] Building FRIDAY Frontend (Vite)...
cd frontend
call npm run build

echo.
echo [3/3] Packaging FRIDAY Desktop App (Electron)...
call npx electron-builder --win --x64
cd ..

echo.
echo Build Complete! Check frontend\dist-electron\win-unpacked for the executable.
pause
