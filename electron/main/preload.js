const { contextBridge, ipcRenderer } = require('electron');

function subscribe(channel, callback) {
  const listener = (event, ...args) => callback(event, ...args);
  ipcRenderer.on(channel, listener);
  return () => ipcRenderer.removeListener(channel, listener);
}

const electronAPI = {
  // Orb control methods
  orbQuery: (text) => ipcRenderer.invoke('orb-query', text),
  orbResearch: (query, domains = []) => ipcRenderer.invoke('orb:research', query, domains),
  serviceControl: (serviceId, action = 'status', payload = {}) => ipcRenderer.invoke('orb:service-control', serviceId, action, payload),
  orbSpeak: (text, emotion = 'thoughtful_warm') => ipcRenderer.invoke('orb:speak', text, emotion),
  openSearch: (query, mode = 'web') => ipcRenderer.invoke('orb:open-search', query, mode),
  dispatchPrimeOrbCommand: (command = {}) => ipcRenderer.invoke('orb:dispatch-command', command),
  listenOnce: () => ipcRenderer.invoke('orb:listen-once'),
  setListening: (enabled) => ipcRenderer.invoke('orb:set-listening', enabled),
  orbCursorMove: (x, y) => ipcRenderer.invoke('orb:cursor-move', x, y),
  getOrbStatus: () => ipcRenderer.invoke('orb:get-status'),
  startDesktopMcp: () => ipcRenderer.invoke('orb-desktop-mcp:start'),
  getDesktopMcpStatus: () => ipcRenderer.invoke('orb-desktop-mcp:status'),
  listDesktopMcpTools: () => ipcRenderer.invoke('orb-desktop-mcp:list-tools'),
  callDesktopMcpTool: (name, args = {}) => ipcRenderer.invoke('orb-desktop-mcp:call-tool', name, args),
  reviewDesktopCognition: (command, context = {}) => ipcRenderer.invoke('orb-desktop-mcp:review', command, context),
  setDesktopMcpActionsEnabled: (enabled) => ipcRenderer.invoke('orb-desktop-mcp:set-actions-enabled', enabled),
  discoverLocalLlm: (extraEndpoints = []) => ipcRenderer.invoke('orb:discover-local-llm', extraEndpoints),
  completeDockTransition: () => ipcRenderer.invoke('orb:dock-transition-complete'),
  getOrbVisibility: () => ipcRenderer.invoke('orb:get-visibility'),
  getOrbDockedState: () => ipcRenderer.invoke('orb:get-docked-state'),
  launchOrbFromDock: () => ipcRenderer.invoke('orb:launch-from-dock'),
  setOrbVisibility: (visible) => ipcRenderer.invoke('orb:set-visibility', visible),
  setOrbState: (setting, value) => ipcRenderer.invoke('orb:set-state', setting, value),
  setOrbSkin: (imageUrl) => ipcRenderer.invoke('orb:set-skin', imageUrl),
  ingestOrbSkin: (sourcePath) => ipcRenderer.invoke('orb:ingest-skin', sourcePath),
  setSkinConfig: (config) => ipcRenderer.invoke('orb:set-skin-config', config),

  // Window control methods
  minimizeWindow: () => ipcRenderer.invoke('window:minimize'),
  closeWindow: () => ipcRenderer.invoke('window:close'),
  setIgnoreMouseEvents: (ignore, options) => ipcRenderer.invoke('window:set-ignore-mouse-events', ignore, options),

  // Settings
  openSettings: () => ipcRenderer.send('open-settings'),

  // Dashboard
  sendSettings: (settings) => ipcRenderer.send('orb:settings', settings),
  openDockStation: () => ipcRenderer.invoke('dock-station:open'),

  // Event listeners
  onOrbPositionUpdate: (callback) => subscribe('orb:position-update', callback),
  onOrbStatusChange: (callback) => subscribe('orb:status-change', callback),
  onOrbVisibilityChanged: (callback) => subscribe('orb:visibility-changed', callback),
  onOrbLaunchSequence: (callback) => subscribe('orb:launch-sequence', callback),
  onOrbDockedState: (callback) => subscribe('orb:docked-state', callback),
  onDockTransition: (callback) => subscribe('orb:dock-transition', callback),
  onCognitivePulse: (callback) => subscribe('orb:cognitive-pulse', callback),
  onEGFState: (callback) => subscribe('orb:egf-state', callback),
  onSpeechPulse: (callback) => subscribe('orb:speech-pulse', callback),
  onVerbalCommand: (callback) => subscribe('orb:verbal-command', callback),
  onPrimeOrbCommand: (callback) => subscribe('orb:prime-command', callback),
  onOrbBridgeMessage: (callback) => subscribe('orb:bridge-message', callback),
  onOrbSkinUpdated: (callback) => subscribe('orb:skin-updated', callback),
  onSkinConfigUpdated: (callback) => subscribe('orb:skin-config-updated', callback),
  onHysteresis: (callback) => subscribe('orb:hysteresis', callback),
  onSettingsUpdate: (callback) => subscribe('update-orb-settings', callback),
  onOpenSettings: (callback) => subscribe('open-settings', callback),
  onSpeak: (callback) => subscribe('speak', callback),

  // Chat / communication channel
  orbChat: (text) => ipcRenderer.invoke('orb:chat', text),
  onChatMessage: (callback) => subscribe('orb:chat-message', callback),

  // Studio window
  openStudio: () => ipcRenderer.invoke('orb:open-studio'),
  openLocalApp: (appId) => ipcRenderer.invoke('orb:open-local-app', appId),
  onStudioConnected: (callback) => subscribe('orb:studio-connected', callback),
  onStudioClosed: (callback) => subscribe('orb:studio-closed', callback),

  // Mesh
  getMeshRegistry: () => ipcRenderer.invoke('orb:mesh-registry'),

  // CRM + Email bridge
  crmRequest: (payload) => ipcRenderer.invoke('orb:crm-request', payload || {}),
  emailRequest: (payload) => ipcRenderer.invoke('orb:email-request', payload || {}),

  // HLSF live field
  onHLSFSnapshot: (callback) => subscribe('orb:hlsf-snapshot', callback),
};

if (process.contextIsolated) {
  contextBridge.exposeInMainWorld('electronAPI', electronAPI);
} else {
  window.electronAPI = electronAPI;
}
