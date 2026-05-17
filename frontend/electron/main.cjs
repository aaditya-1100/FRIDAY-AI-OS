const { app, BrowserWindow, session } = require('electron');
const path = require('path');
const { spawn, execSync } = require('child_process');
const http = require('http');

let mainWindow;
let backendProcess;
let isQuitting = false;

// ── Kill an entire Windows process tree by PID ──────────────────────────────
function killProcessTree(pid) {
  if (!pid) return;
  try {
    // /F = force, /T = include child tree, /PID = target PID
    execSync(`taskkill /F /T /PID ${pid}`, { stdio: 'ignore' });
    console.log(`[SHUTDOWN] Killed process tree for PID ${pid}`);
  } catch (e) {
    // Process may already be gone
    console.log(`[SHUTDOWN] taskkill returned (process may already be dead): ${e.message}`);
  }
}

// ── Kill any leftover uvicorn / python processes on port 8001 ───────────────
function killPortProcess(port) {
  try {
    // Find PID using the port, then kill it
    const result = execSync(`netstat -ano | findstr :${port}`, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] });
    const lines = result.split('\n');
    const pids = new Set();
    for (const line of lines) {
      const parts = line.trim().split(/\s+/);
      const lastPart = parts[parts.length - 1];
      if (lastPart && /^\d+$/.test(lastPart) && lastPart !== '0') {
        pids.add(lastPart);
      }
    }
    for (const pid of pids) {
      try {
        execSync(`taskkill /F /T /PID ${pid}`, { stdio: 'ignore' });
        console.log(`[SHUTDOWN] Killed PID ${pid} on port ${port}`);
      } catch (e) {
        // Already dead — fine
      }
    }
  } catch (e) {
    // netstat found nothing — port already free
  }
}

function startBackend() {
  const backendPath = 'C:\\FRIDAY\\backend';
  const pythonExe = 'C:\\FRIDAY\\.venv\\Scripts\\python.exe';
  backendProcess = spawn(pythonExe, ['-m', 'uvicorn', 'api.server:app', '--host', '127.0.0.1', '--port', '8001'], {
    cwd: backendPath,
    shell: true,
    // detached: false ensures it's a child of this Electron process
    detached: false,
  });

  backendProcess.stdout.on('data', (data) => console.log(`Backend: ${data}`));
  backendProcess.stderr.on('data', (data) => console.error(`Backend Error: ${data}`));

  backendProcess.on('exit', (code) => {
    console.log(`[BACKEND] Process exited with code ${code}`);
    backendProcess = null;
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 600,
    height: 800,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      autoplayPolicy: 'no-user-gesture-required'
    },
    autoHideMenuBar: true,
    title: 'FRIDAY',
    icon: path.join(__dirname, '../public/favicon.ico')
  });

  // Grant microphone permission automatically
  session.defaultSession.setPermissionRequestHandler((webContents, permission, callback) => {
    callback(permission === 'media');
  });

  const isDev = process.env.NODE_ENV === 'development';

  if (isDev) {
    waitForVite('localhost', 5173, 30, () => {
      mainWindow.loadURL('http://localhost:5173');
    });
  } else {
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html'));
  }

  // Intercept close — run full shutdown synchronously before quitting
  mainWindow.on('close', (e) => {
    if (!isQuitting) {
      e.preventDefault();
      performShutdown();
    }
  });
}

// ── Full synchronous shutdown ────────────────────────────────────────────────
function performShutdown() {
  if (isQuitting) return;
  isQuitting = true;
  console.log('[SHUTDOWN] Initiating full process teardown...');

  // 1. Kill backend process tree
  if (backendProcess && backendProcess.pid) {
    killProcessTree(backendProcess.pid);
    backendProcess = null;
  }

  // 2. Belt-and-suspenders: kill anything still on port 8001
  killPortProcess(8001);

  // 3. Quit Electron (and Vite dev server is killed by concurrently -k)
  console.log('[SHUTDOWN] All backend processes terminated. Quitting Electron.');
  app.quit();
}

// ── Poll until Vite dev server responds, then call onReady() ────────────────
function waitForVite(host, port, retriesLeft, onReady) {
  const req = http.request({ host, port, path: '/', method: 'GET', timeout: 1000 }, () => {
    onReady();
  });
  req.on('error', () => {
    if (retriesLeft <= 0) {
      console.error('Vite dev server never started. Run "npm run dev" in the frontend folder.');
      return;
    }
    setTimeout(() => waitForVite(host, port, retriesLeft - 1, onReady), 1000);
  });
  req.on('timeout', () => req.destroy());
  req.end();
}

app.whenReady().then(() => {
  startBackend();
  setTimeout(createWindow, 1000);

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    performShutdown();
  }
});

// Catch any quit triggered by other means (e.g. taskbar right-click quit)
app.on('before-quit', () => {
  if (!isQuitting) {
    performShutdown();
  }
});
