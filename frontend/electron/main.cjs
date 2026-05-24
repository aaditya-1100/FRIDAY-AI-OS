const { app, BrowserWindow, session } = require('electron');
const path = require('path');
const { spawn, execSync } = require('child_process');
const http = require('http');
const fs = require('fs');
const WebSocket = require('ws');


// ── Single Instance Lock ────────────────────────────────────────────────────
const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
  console.log('[STARTUP] Another instance of FRIDAY is already running. Exiting.');
  app.quit();
  process.exit(0);
}

let mainWindow;
let backendProcess;
let isQuitting = false;

// ── Watchdog State Variables ────────────────────────────────────────────────
let wsClient;
let pingInterval;
let missedPongs = 0;
let isReconnecting = false;
let restartCount = 0;
let lastRestartTime = 0;

// ── Log system events directly to the runtime log file ──────────────────────
function logToFile(message) {
  const timestamp = new Date().toISOString().replace('T', ' ').substring(0, 19);
  const logMessage = `[ELECTRON ${timestamp}] ${message}\n`;
  try {
    const isPacked = app.isPackaged;
    const appRoot = isPacked 
      ? path.join(process.execPath, '..', '..', '..', '..')
      : path.join(__dirname, '..', '..');
    const logPath = path.join(appRoot, 'backend', 'friday_runtime.log');
    fs.appendFileSync(logPath, logMessage);
  } catch (e) {
    // Fail silently if log path isn't writable yet
  }
}

// ── Kill an entire Windows process tree by PID ──────────────────────────────
function killProcessTree(pid) {
  if (!pid) return;
  try {
    execSync(`taskkill /F /T /PID ${pid}`, { stdio: 'ignore' });
    logToFile(`[SHUTDOWN] Killed process tree for PID ${pid}`);
  } catch (e) {
    logToFile(`[SHUTDOWN] taskkill returned: ${e.message}`);
  }
}

// ── Kill any leftover uvicorn / python processes on port 8001 ───────────────
function killPortProcess(port) {
  try {
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
        logToFile(`[CLEANUP] Killed PID ${pid} dangling on port ${port}`);
      } catch (e) {
        // already dead
      }
    }
  } catch (e) {
    // netstat found nothing — port free
  }
}

function startBackend() {
  const isPacked = app.isPackaged;

  // In dev mode: project root is 2 levels up from electron/main.cjs → C:\FRIDAY
  // In packed mode (electron-packager): FRIDAY.exe is at
  //   frontend/dist-electron/FRIDAY-win32-x64/FRIDAY.exe
  // Going up 4 levels from the exe gets us to C:\FRIDAY (project root)
  //
  // Path resolution priority:
  //   1. Dev: __dirname/../.. (C:\FRIDAY)
  //   2. Packed: execPath/../../../../ (C:\FRIDAY)
  //   3. Packed fallback: hardcoded project root detection via resources path

  let appRoot, backendPath, pythonExe;

  if (!isPacked) {
    // Development: electron/main.cjs → frontend → project root
    appRoot = path.join(__dirname, '..', '..');
    backendPath = path.join(appRoot, 'backend');
    pythonExe = path.join(appRoot, '.venv', 'Scripts', 'python.exe');
  } else {
    // Packaged: FRIDAY.exe is at dist-electron/FRIDAY-win32-x64/FRIDAY.exe
    // Go up: FRIDAY-win32-x64 → dist-electron → frontend → C:\FRIDAY
    const exeDir = path.dirname(process.execPath);       // FRIDAY-win32-x64
    appRoot = path.join(exeDir, '..', '..', '..');        // C:\FRIDAY\frontend\dist-electron\.. → C:\FRIDAY
    backendPath = path.join(appRoot, 'backend');
    pythonExe = path.join(appRoot, '.venv', 'Scripts', 'python.exe');

    // Fallback: try one more level if backend doesn't exist
    if (!fs.existsSync(backendPath)) {
      appRoot = path.join(exeDir, '..', '..', '..', '..');
      backendPath = path.join(appRoot, 'backend');
      pythonExe = path.join(appRoot, '.venv', 'Scripts', 'python.exe');
    }
  }

  logToFile(`[STARTUP] isPacked     = ${isPacked}`);
  logToFile(`[STARTUP] appRoot      = ${appRoot}`);
  logToFile(`[STARTUP] backendPath  = ${backendPath}`);
  logToFile(`[STARTUP] pythonExe    = ${pythonExe}`);
  logToFile(`[STARTUP] backendExist = ${fs.existsSync(backendPath)}`);
  logToFile(`[STARTUP] pythonExists = ${fs.existsSync(pythonExe)}`);

  if (!fs.existsSync(pythonExe)) {
    logToFile(`[CRITICAL] Python executable not found at ${pythonExe}! Backend will fail to start.`);
    return;
  }

  // Use shell: false for stable direct process execution (avoids cmd.exe zombie trees)
  backendProcess = spawn(pythonExe, ['-m', 'uvicorn', 'api.server:app', '--host', '127.0.0.1', '--port', '8001'], {
    cwd: backendPath,
    shell: false,
    detached: false,
    env: { ...process.env, PYTHONUNBUFFERED: '1' }
  });

  backendProcess.stdout.on('data', (data) => {
    logToFile(`[BACKEND STDOUT] ${data.toString().trim()}`);
  });

  backendProcess.stderr.on('data', (data) => {
    logToFile(`[BACKEND STDERR] ${data.toString().trim()}`);
  });

  backendProcess.on('exit', (code) => {
    logToFile(`[BACKEND EXIT] Process exited with code ${code}`);
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

  mainWindow.on('close', (e) => {
    if (!isQuitting) {
      e.preventDefault();
      performShutdown();
    }
  });
}

function setupBackendWatchdog() {
  if (isQuitting) return;

  // Clear existing intervals
  if (pingInterval) {
    clearInterval(pingInterval);
    pingInterval = null;
  }

  if (wsClient) {
    try {
      wsClient.terminate();
    } catch (e) {}
    wsClient = null;
  }

  logToFile('[WATCHDOG] Initializing WebSocket watchdog...');
  missedPongs = 0;

  try {
    wsClient = new WebSocket('ws://127.0.0.1:8001/api/ws');

    wsClient.on('open', () => {
      logToFile('[WATCHDOG] Connection established with backend WebSocket');
      missedPongs = 0;

      // Start sending pings every 5 seconds
      pingInterval = setInterval(() => {
        if (isQuitting) return;
        if (wsClient && wsClient.readyState === WebSocket.OPEN) {
          try {
            wsClient.send(JSON.stringify({ type: 'ping' }));
            missedPongs++;
            
            if (missedPongs >= 3) {
              logToFile(`[WATCHDOG CRITICAL] 3 consecutive pings unanswered! Missed pongs: ${missedPongs}`);
              handleBackendFailure();
            }
          } catch (err) {
            logToFile(`[WATCHDOG ERROR] Failed to send ping: ${err.message}`);
            handleBackendFailure();
          }
        } else {
          logToFile('[WATCHDOG WARNING] WebSocket not open, triggering restart check...');
          handleBackendFailure();
        }
      }, 5000);
    });

    wsClient.on('message', (data) => {
      try {
        const msg = JSON.parse(data.toString());
        if (msg.type === 'pong') {
          missedPongs = 0; // reset
        }
      } catch (err) {
        // Not a JSON message or different payload
      }
    });

    wsClient.on('error', (err) => {
      logToFile(`[WATCHDOG ERROR] WebSocket error: ${err.message}`);
    });

    wsClient.on('close', (code, reason) => {
      logToFile(`[WATCHDOG] WebSocket connection closed: code=${code}, reason=${reason}`);
      if (!isQuitting && !isReconnecting) {
        isReconnecting = true;
        setTimeout(() => {
          isReconnecting = false;
          setupBackendWatchdog();
        }, 3000);
      }
    });
  } catch (err) {
    logToFile(`[WATCHDOG CRITICAL] Failed to instantiate WebSocket: ${err.message}`);
    handleBackendFailure();
  }
}

function handleBackendFailure() {
  if (isQuitting) return;

  logToFile('[WATCHDOG CRITICAL] Backend process hang or crash detected!');

  // Prevent infinite restart loops
  const now = Date.now();
  if (now - lastRestartTime < 60000) {
    restartCount++;
  } else {
    restartCount = 1;
  }
  lastRestartTime = now;

  if (restartCount > 3) {
    logToFile('[WATCHDOG FATAL] Too many backend restarts in a short time. Giving up to prevent loops.');
    if (pingInterval) {
      clearInterval(pingInterval);
      pingInterval = null;
    }
    return;
  }

  // Clear interval
  if (pingInterval) {
    clearInterval(pingInterval);
    pingInterval = null;
  }
  if (wsClient) {
    try {
      wsClient.terminate();
    } catch (e) {}
    wsClient = null;
  }

  logToFile('[WATCHDOG] Restarting backend...');
  
  // 1. Kill backend process tree
  if (backendProcess && backendProcess.pid) {
    killProcessTree(backendProcess.pid);
    backendProcess = null;
  }
  
  // 2. Free port 8001
  killPortProcess(8001);

  // 3. Restart
  startBackend();

  // 4. Wait for it to be ready and re-establish watchdog
  setTimeout(() => {
    waitForBackend('127.0.0.1', 8001, 15, () => {
      if (!isQuitting) {
        setupBackendWatchdog();
      }
    });
  }, 2000);
}

function performShutdown() {
  if (isQuitting) return;
  isQuitting = true;
  logToFile('[SHUTDOWN] Initiating full process teardown...');

  if (pingInterval) {
    clearInterval(pingInterval);
    pingInterval = null;
  }
  if (wsClient) {
    try {
      wsClient.terminate();
    } catch (e) {}
    wsClient = null;
  }

  if (backendProcess && backendProcess.pid) {
    logToFile(`[SHUTDOWN] Killing backend process tree (PID ${backendProcess.pid})`);
    killProcessTree(backendProcess.pid);
    backendProcess = null;
  }

  killPortProcess(8001);
  logToFile('[SHUTDOWN] All backend processes terminated. Quitting Electron.');
  app.quit();
}

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

function waitForBackend(host, port, retriesLeft, onReady) {
  const req = http.request({ host, port, path: '/api/health', method: 'GET', timeout: 1500 }, (res) => {
    logToFile(`[STARTUP] Backend health check: HTTP ${res.statusCode}`);
    onReady();
  });
  req.on('error', () => {
    if (retriesLeft <= 0) {
      logToFile('[STARTUP] Backend never started after max retries. Opening window anyway...');
      onReady();
      return;
    }
    setTimeout(() => waitForBackend(host, port, retriesLeft - 1, onReady), 1000);
  });
  req.on('timeout', () => { req.destroy(); });
  req.end();
}

app.on('second-instance', (event, commandLine, workingDirectory) => {
  logToFile('[STARTUP] Second instance launched. Focusing existing window...');
  if (mainWindow) {
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.focus();
  }
});

app.whenReady().then(() => {
  logToFile('[STARTUP] Electron app ready. Cleaning up port 8001 to prevent stale backends...');
  killPortProcess(8001);
  
  logToFile('[STARTUP] Starting backend server...');
  startBackend();
  
  logToFile('[STARTUP] Waiting for backend to be ready...');
  waitForBackend('127.0.0.1', 8001, 30, () => {
    logToFile('[STARTUP] Backend ready. Creating window...');
    createWindow();
    setupBackendWatchdog();
  });

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    performShutdown();
  }
});

app.on('before-quit', () => {
  if (!isQuitting) {
    performShutdown();
  }
});
