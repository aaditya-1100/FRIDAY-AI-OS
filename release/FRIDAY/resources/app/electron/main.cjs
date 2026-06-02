const { app, BrowserWindow, session } = require('electron');
const path = require('path');
const { spawn, execSync } = require('child_process');
const http = require('http');
const fs = require('fs');

// Set Application User Model ID for robust Windows taskbar pinning and grouping
app.setAppUserModelId('com.friday.assistant');

// ── Single Instance Lock ────────────────────────────────────────────────────
const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
  console.log('[STARTUP] Another instance of FRIDAY is already running. Exiting.');
  app.quit();
  process.exit(0);
}

let mainWindow = null;
let backendProcess = null;
let isQuitting = false;

// ── Watchdog State Variables ────────────────────────────────────────────────
let pingInterval = null;
let missedPongs = 0;
let isReconnecting = false;
let restartCount = 0;
let lastRestartTime = 0;

// ── App Root Caching & Log system events directly to the runtime log file ───
let cachedPaths = null;
function getAppPaths() {
  if (cachedPaths) return cachedPaths;

  let currentDir = app.isPackaged 
    ? path.dirname(process.execPath)
    : __dirname;

  let foundPython = null;
  let foundBackend = null;

  // Search up to 5 levels high to locate the virtual env and backend root
  for (let i = 0; i < 6; i++) {
    const possibleVenvPy = path.join(currentDir, '.venv', 'Scripts', 'python.exe');
    const possibleBackend = path.join(currentDir, 'backend');

    if (!foundPython && fs.existsSync(possibleVenvPy)) {
      foundPython = possibleVenvPy;
    }
    if (!foundBackend && fs.existsSync(possibleBackend)) {
      foundBackend = possibleBackend;
    }

    if (foundPython && foundBackend) {
      break;
    }

    const parent = path.dirname(currentDir);
    if (parent === currentDir) break; // Reached root
    currentDir = parent;
  }

  // If not found in parent traversal, try default absolute and relative fallbacks
  if (!foundPython) {
    const rootVenvPy = 'C:\\FRIDAY\\.venv\\Scripts\\python.exe';
    if (fs.existsSync(rootVenvPy)) {
      foundPython = rootVenvPy;
    } else {
      foundPython = 'python.exe'; // fallback to path
    }
  }
  if (!foundBackend) {
    const rootBackend = 'C:\\FRIDAY\\backend';
    if (fs.existsSync(rootBackend)) {
      foundBackend = rootBackend;
    } else {
      foundBackend = path.join(__dirname, '..', '..', 'backend'); // best guess
    }
  }

  cachedPaths = { pythonExe: foundPython, backendPath: foundBackend };
  return cachedPaths;
}

// ── Active Timeout Pruning Garbage Collector ──────────────────────────────
let activeTimeouts = [];
function safeSetTimeout(fn, delay) {
  const id = setTimeout(() => {
    activeTimeouts = activeTimeouts.filter(t => t !== id);
    fn();
  }, delay);
  activeTimeouts.push(id);
  return id;
}

function clearAllTimeouts() {
  for (const id of activeTimeouts) {
    clearTimeout(id);
  }
  activeTimeouts = [];
}

function logToFile(message) {
  if (isQuitting) return; // Immediate teardown guard to prevent destroyed exceptions
  const timestamp = new Date().toISOString().replace('T', ' ').substring(0, 19);
  const logMessage = `[ELECTRON ${timestamp}] ${message}\n`;
  try {
    const { backendPath } = getAppPaths();
    const logPath = path.join(backendPath, 'friday_runtime.log');
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
  if (isQuitting) return;

  const { pythonExe, backendPath } = getAppPaths();

  let isPacked = app.isPackaged;

  logToFile(`[STARTUP] isPacked     = ${isPacked}`);
  logToFile(`[STARTUP] backendPath  = ${backendPath}`);
  logToFile(`[STARTUP] pythonExe    = ${pythonExe}`);
  logToFile(`[STARTUP] backendExist = ${fs.existsSync(backendPath)}`);
  logToFile(`[STARTUP] pythonExists = ${fs.existsSync(pythonExe)}`);

  if (!fs.existsSync(pythonExe)) {
    logToFile(`[CRITICAL] Python executable not found at ${pythonExe}! Backend will fail to start.`);
    return;
  }

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
  if (isQuitting) return;

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

  // Capture all frontend console messages and pipe them to the unified log file with strict window guards
  mainWindow.webContents.on('console-message', (event, level, message, line, sourceId) => {
    if (isQuitting || !mainWindow || mainWindow.isDestroyed()) return;
    const levelStr = ['DEBUG', 'INFO', 'WARN', 'ERROR'][level] || 'LOG';
    logToFile(`[FRONTEND CONSOLE] [${levelStr}] ${message}`);
  });

  session.defaultSession.setPermissionRequestHandler((webContents, permission, callback) => {
    if (isQuitting) {
      callback(false);
      return;
    }
    callback(permission === 'media');
  });

  // Bypass iframe security restrictions dynamically to allow maps.google.com inside local file:// origin
  session.defaultSession.webRequest.onHeadersReceived((details, callback) => {
    const responseHeaders = { ...details.responseHeaders };
    Object.keys(responseHeaders).forEach(header => {
      const lower = header.toLowerCase();
      if (lower === 'x-frame-options' || lower === 'content-security-policy') {
        delete responseHeaders[header];
      }
    });
    callback({ cancel: false, responseHeaders });
  });

  const isDev = process.env.NODE_ENV === 'development';

  if (isDev) {
    waitForVite('localhost', 5173, 30, () => {
      if (isQuitting || !mainWindow || mainWindow.isDestroyed()) return;
      mainWindow.loadURL('http://localhost:5173');
    });
  } else {
    const indexPath = path.join(__dirname, '..', 'dist', 'index.html');
    logToFile(`[WINDOW] Loading index.html from: ${indexPath} (exists=${fs.existsSync(indexPath)})`);
    if (isQuitting || !mainWindow || mainWindow.isDestroyed()) return;
    mainWindow.loadFile(indexPath);
  }

  mainWindow.on('close', (e) => {
    if (!isQuitting) {
      e.preventDefault();
      performShutdown();
    }
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

function setupBackendWatchdog() {
  if (isQuitting) return;

  if (pingInterval) {
    clearInterval(pingInterval);
    pingInterval = null;
  }

  logToFile('[WATCHDOG] Initializing HTTP health check watchdog...');
  missedPongs = 0;

  pingInterval = setInterval(() => {
    if (isQuitting) {
      if (pingInterval) {
        clearInterval(pingInterval);
        pingInterval = null;
      }
      return;
    }

    const req = http.request({
      host: '127.0.0.1',
      port: 8001,
      path: '/api/health',
      method: 'GET',
      timeout: 2000
    }, (res) => {
      if (isQuitting) return;
      if (res.statusCode === 200) {
        missedPongs = 0;
      } else {
        logToFile(`[WATCHDOG WARNING] Health check returned status: ${res.statusCode}`);
        missedPongs++;
        if (missedPongs >= 6) {
          logToFile(`[WATCHDOG CRITICAL] 6 consecutive health checks failed!`);
          handleBackendFailure();
        }
      }
    });

    req.on('error', (err) => {
      if (isQuitting) return;
      logToFile(`[WATCHDOG ERROR] Health check failed: ${err.message}`);
      missedPongs++;
      if (missedPongs >= 6) {
        logToFile(`[WATCHDOG CRITICAL] 6 consecutive health checks failed!`);
        handleBackendFailure();
      }
    });

    req.on('timeout', () => {
      req.destroy();
    });

    req.end();
  }, 5000);
}

function handleBackendFailure() {
  if (isQuitting) return;

  logToFile('[WATCHDOG CRITICAL] Backend process hang or crash detected!');

  const now = Date.now();
  if (now - lastRestartTime < 60000) {
    restartCount++;
  } else {
    restartCount = 1;
  }
  lastRestartTime = now;

  if (restartCount > 5) {
    logToFile('[WATCHDOG DEGRADED] Too many backend restarts in a short time. Switching to degraded offline mode to preserve Electron UI.');
    if (pingInterval) {
      clearInterval(pingInterval);
      pingInterval = null;
    }
    if (mainWindow && !mainWindow.isDestroyed()) {
      try {
        mainWindow.webContents.send('backend-status', { status: 'degraded', reason: 'too_many_restarts' });
      } catch (e) {
        // fail silently if ipc not ready
      }
    }
    return;
  }

  if (pingInterval) {
    clearInterval(pingInterval);
    pingInterval = null;
  }

  logToFile('[WATCHDOG] Restarting backend...');
  
  if (backendProcess && backendProcess.pid) {
    killProcessTree(backendProcess.pid);
    backendProcess = null;
  }
  
  killPortProcess(8001);
  startBackend();

  safeSetTimeout(() => {
    if (isQuitting) return;
    waitForBackend('127.0.0.1', 8001, 15, () => {
      if (isQuitting) return;
      setupBackendWatchdog();
    });
  }, 2000);
}

function performShutdown() {
  if (isQuitting) return;
  isQuitting = true;
  clearAllTimeouts(); // Cleanly prune all active pending setTimeout tasks
  logToFile('[SHUTDOWN] Initiating full process teardown...');

  if (pingInterval) {
    clearInterval(pingInterval);
    pingInterval = null;
  }

  if (backendProcess && backendProcess.pid) {
    logToFile(`[SHUTDOWN] Killing backend process tree (PID ${backendProcess.pid})`);
    killProcessTree(backendProcess.pid);
    backendProcess = null;
  }

  killPortProcess(8001);
  logToFile('[SHUTDOWN] All backend processes terminated. Quitting Electron.');

  // Cleanly dismiss window references
  if (mainWindow) {
    if (!mainWindow.isDestroyed()) {
      mainWindow.destroy();
    }
    mainWindow = null;
  }

  app.quit();
}

function waitForVite(host, port, retriesLeft, onReady) {
  if (isQuitting) return;

  const req = http.request({ host, port, path: '/', method: 'GET', timeout: 1000 }, () => {
    if (isQuitting) return;
    onReady();
  });
  req.on('error', () => {
    if (isQuitting) return;
    if (retriesLeft <= 0) {
      console.error('Vite dev server never started. Run "npm run dev" in the frontend folder.');
      return;
    }
    safeSetTimeout(() => {
      if (isQuitting) return;
      waitForVite(host, port, retriesLeft - 1, onReady);
    }, 1000);
  });
  req.on('timeout', () => req.destroy());
  req.end();
}

function waitForBackend(host, port, retriesLeft, onReady) {
  if (isQuitting) return;

  const req = http.request({ host, port, path: '/api/health', method: 'GET', timeout: 1500 }, (res) => {
    if (isQuitting) return;
    logToFile(`[STARTUP] Backend health check: HTTP ${res.statusCode}`);
    onReady();
  });
  req.on('error', () => {
    if (isQuitting) return;
    if (retriesLeft <= 0) {
      logToFile('[STARTUP] Backend never started after max retries. Opening window anyway...');
      onReady();
      return;
    }
    safeSetTimeout(() => {
      if (isQuitting) return;
      waitForBackend(host, port, retriesLeft - 1, onReady);
    }, 1000);
  });
  req.on('timeout', () => { req.destroy(); });
  req.end();
}

app.on('second-instance', (event, commandLine, workingDirectory) => {
  logToFile('[STARTUP] Second instance launched. Focusing existing window...');
  if (mainWindow && !mainWindow.isDestroyed()) {
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.focus();
  }
});

app.whenReady().then(() => {
  logToFile('[STARTUP] Electron app ready. Cleaning up port 8001 to prevent stale backends...');
  killPortProcess(8001);
  
  logToFile('[STARTUP] Port cleaned up. Waiting 600ms for OS sockets and PortAudio endpoints to release...');
  safeSetTimeout(() => {
    if (isQuitting) return;
    logToFile('[STARTUP] Starting backend server...');
    startBackend();
    
    logToFile('[STARTUP] Waiting for backend to be ready...');
    waitForBackend('127.0.0.1', 8001, 30, () => {
      if (isQuitting) return;
      logToFile('[STARTUP] Backend ready. Creating window...');
      createWindow();
      setupBackendWatchdog();
    });
  }, 600);

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
