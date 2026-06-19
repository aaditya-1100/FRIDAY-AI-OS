const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  setNotchState: (stateInfo) => ipcRenderer.send('set-notch-state', stateInfo),
  onHotkeyMicOn: (callback) => {
    const sub = () => callback();
    ipcRenderer.on('hotkey-mic-on', sub);
    return () => ipcRenderer.removeListener('hotkey-mic-on', sub);
  },
  onHotkeyMicOff: (callback) => {
    const sub = () => callback();
    ipcRenderer.on('hotkey-mic-off', sub);
    return () => ipcRenderer.removeListener('hotkey-mic-off', sub);
  },
  openMainWindow: () => ipcRenderer.send('open-main-window'),
  toggleNotchVisibility: (visible) => ipcRenderer.send('toggle-notch-visibility', { visible }),
  getNotchConfig: () => ipcRenderer.invoke('get-notch-config'),
  isBackendReady: () => ipcRenderer.invoke('is-backend-ready'),
  onBackendReady: (callback) => {
    const sub = () => callback();
    ipcRenderer.on('backend-ready', sub);
    return () => ipcRenderer.removeListener('backend-ready', sub);
  },
  setIgnoreMouseEvents: (ignore, forward) => ipcRenderer.send('set-ignore-mouse-events', { ignore, forward }),
  showNotchContextMenu: () => ipcRenderer.send('show-notch-context-menu'),
  onWindowVisibilityChange: (callback) => {
    const sub = (event, { visible }) => callback(visible);
    ipcRenderer.on('window-visibility-change', sub);
    return () => ipcRenderer.removeListener('window-visibility-change', sub);
  },
});
