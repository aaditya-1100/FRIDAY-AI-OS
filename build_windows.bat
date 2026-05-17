@echo off
echo [1/3] Building FRIDAY Backend (PyInstaller)...
cd backend
python -m pip install pyinstaller
python -m PyInstaller --name "FridayBackend" --onefile --noconsole api/server.py
cd ..

echo [2/3] Building FRIDAY Frontend (Vite)...
cd frontend
call npm run build

echo [3/3] Packaging FRIDAY Desktop App (Electron)...
call npm install electron-builder -D
call npx electron-builder --win --x64
cd ..

echo Build Complete! Check frontend\dist for the installer.
pause
