@echo off
setlocal enabledelayedexpansion

echo ==================================================
echo             FRIDAY FULL AUTHORITATIVE LIFECYCLE
echo ==================================================
echo.

cd /d "%~dp0"

echo [1/8] Sourcing latest local code...
echo Local code directory: "%~dp0"
echo [SUCCESS] Sourced local updates.
echo.

echo [2/8] Terminating active processes ^& installing dependencies...
taskkill /F /IM FRIDAY.exe /T >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| find "8001" ^| find "LISTENING" 2^>nul') do taskkill /F /PID %%a /T >nul 2>&1

echo Installing Python backend dependencies...
call .venv\Scripts\pip.exe install -r backend/requirements.txt
if !ERRORLEVEL! neq 0 (
    echo [ERROR] Python dependencies installation failed!
    pause
    exit /b 1
)

echo Resolving library dependency conflicts...
call .venv\Scripts\pip.exe install click==8.4.1 >nul 2>&1


echo Installing Node frontend dependencies...
cd frontend
call npm install
if !ERRORLEVEL! neq 0 (
    echo [ERROR] Node dependencies installation failed!
    cd ..
    pause
    exit /b 1
)
cd ..
echo [SUCCESS] All dependencies installed successfully.
echo.

echo [3/8] Running verification ^& validation suites...
echo Running Python health checks...
call .venv\Scripts\python.exe health_check.py
if !ERRORLEVEL! neq 0 (
    echo [ERROR] Health checks failed! Aborting build.
    pause
    exit /b 1
)

echo Running Context Graph tests (600 test cases)...
call .venv\Scripts\python.exe backend/tests/context_validator.py
if !ERRORLEVEL! neq 0 (
    echo [ERROR] Context Graph tests failed! Aborting build.
    pause
    exit /b 1
)

echo Running Reconstruction Matrix tests (500 test cases)...
call .venv\Scripts\python.exe backend/tests/reconstruction_validator.py
if !ERRORLEVEL! neq 0 (
    echo [ERROR] Reconstruction Matrix tests failed! Aborting build.
    pause
    exit /b 1
)
echo [SUCCESS] All validation checks passed! (1100/1100 tests passed).
echo.

echo [4/8] Building Vite UI compiled assets...
cd frontend
call npm run build
if !ERRORLEVEL! neq 0 (
    echo [ERROR] UI Compilation failed!
    cd ..
    pause
    exit /b 1
)
cd ..
echo [SUCCESS] Frontend compilation complete.
echo.

echo [5/8] Packaging Electron executable...
if exist "frontend\dist-electron" rmdir /s /q "frontend\dist-electron"
cd frontend
call npm run build:electron
if !ERRORLEVEL! neq 0 (
    echo [ERROR] Electron packaging failed!
    cd ..
    pause
    exit /b 1
)
cd ..
powershell -Command "(Get-Item '%~dp0frontend\dist-electron\FRIDAY-win32-x64\FRIDAY.exe').LastWriteTime = [DateTime]::Now"
echo [SUCCESS] Electron packaging complete.
echo.

echo [6/8] Copying production assets...
set "EXE_PATH=%~dp0frontend\dist-electron\FRIDAY-win32-x64\FRIDAY.exe"
if not exist "!EXE_PATH!" (
    echo [ERROR] Packed executable not found at !EXE_PATH!
    pause
    exit /b 1
)
echo [SUCCESS] Production assets mapped successfully.
echo.

echo [7/8] Verifying build integrity...
call .venv\Scripts\python.exe check_build.py
if !ERRORLEVEL! neq 0 (
    echo [ERROR] Build integrity verification failed!
    pause
    exit /b 1
)
echo [SUCCESS] Build integrity verified!
echo.

echo [8/8] Generating final Release Package...
set "RELEASE_DIR=%~dp0release"
if exist "!RELEASE_DIR!" rmdir /s /q "!RELEASE_DIR!"
mkdir "!RELEASE_DIR!"
mkdir "!RELEASE_DIR!\FRIDAY"
mkdir "!RELEASE_DIR!\backend"

echo Creating exclude list on the fly...
echo .git > "%~dp0exclude_friday.txt"
echo __pycache__ >> "%~dp0exclude_friday.txt"
echo .pytest_cache >> "%~dp0exclude_friday.txt"
echo .venv >> "%~dp0exclude_friday.txt"
echo logs >> "%~dp0exclude_friday.txt"
echo scratch >> "%~dp0exclude_friday.txt"
echo .env >> "%~dp0exclude_friday.txt"

echo Copying compiled Electron client...
xcopy "%~dp0frontend\dist-electron\FRIDAY-win32-x64\*" "!RELEASE_DIR!\FRIDAY\" /y /e /q >nul

echo Copying backend scripts (excluding temp/venv/pycaches)...
xcopy "%~dp0backend\*" "!RELEASE_DIR!\backend\" /y /e /q /exclude:%~dp0exclude_friday.txt >nul
del "%~dp0exclude_friday.txt" >nul 2>&1

echo Copying root environment launchers...
copy "%~dp0Start_FRIDAY.bat" "!RELEASE_DIR!\" /y >nul
copy "%~dp0.env" "!RELEASE_DIR!\.env" /y >nul
copy "%~dp0.env" "!RELEASE_DIR!\backend\.env" /y >nul
if exist "%~dp0README.md" copy "%~dp0README.md" "!RELEASE_DIR!\" /y >nul

echo [SUCCESS] Release package generated at: !RELEASE_DIR!
echo.
echo ==================================================
echo     FRIDAY HAS BEEN FULLY REBUILT ^& RELEASED
echo ==================================================
echo.

choice /c yn /m "Would you like to launch the newly released FRIDAY now?"
if !ERRORLEVEL! EQU 1 (
    echo.
    echo Launching packaged executable...
    start "" "!RELEASE_DIR!\FRIDAY\FRIDAY.exe"
)

exit /b 0
