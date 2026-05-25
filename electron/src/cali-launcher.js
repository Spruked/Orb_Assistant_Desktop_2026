const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const EventEmitter = require('events');

/**
 * CALI multi-core launcher.
 *
 * Notes:
 * - Paths are scoped to Orb_Assistant/electron/src/core-bridges to avoid touching core repositories.
 * - Each bridge script is expected to print a line containing "READY" when up, and accept JSON lines on stdin.
 */
class CALILauncher extends EventEmitter {
  constructor(repoRoot) {
    super();
    this.repoRoot = repoRoot;
    this.processes = new Map();
    this.status = {
      kaygee: 'stopped',
      caleon: 'stopped',
      cali: 'stopped',
      cali_x_one: 'stopped',
      ucm_core_ecm: 'stopped'
    };

    this.corePaths = {
      kaygee: path.join(this.repoRoot, 'src', 'core-bridges', 'kaygee.py'),
      caleon: path.join(this.repoRoot, 'src', 'core-bridges', 'caleon.py'),
      cali: path.join(this.repoRoot, 'src', 'core-bridges', 'cali.py'),
      cali_x_one: path.join(this.repoRoot, 'src', 'core-bridges', 'cali_x_one.py'),
      ucm_core_ecm: path.join(this.repoRoot, 'src', 'core-bridges', 'ucm_core_ecm.py'),
    };
  }

  async startAll() {
    this.emit('log', { level: 'info', text: 'Starting CALI UCM_4_Core bridge processes...' });

    const startupOrder = ['ucm_core_ecm', 'caleon', 'cali_x_one', 'kaygee', 'cali'];
    for (const core of startupOrder) {
      await this.startCore(core);
      await this.waitForCoreReady(core, 15000);
    }

    this.emit('log', { level: 'info', text: 'All configured core bridges online' });
  }

  async startCore(coreName) {
    const scriptPath = this.corePaths[coreName];
    if (!scriptPath || !fs.existsSync(scriptPath)) {
      throw new Error(`Core script not found: ${scriptPath}`);
    }

    const proc = spawn(process.env.PYTHON || 'python', [scriptPath, this.repoRoot], {
      cwd: this.repoRoot,
      env: { ...process.env },
      stdio: ['pipe', 'pipe', 'pipe'],
    });

    this.processes.set(coreName, proc);
    this.status[coreName] = 'starting';

    const stdoutHandler = (data) => {
      const line = data.toString();
      if (line.includes('READY')) {
        this.status[coreName] = 'running';
        this.emit('core-status', { core: coreName, status: 'running' });
      }
      this.emit('log', { core: coreName, text: line });
    };

    const stderrHandler = (data) => {
      const line = data.toString();
      this.emit('log', { core: coreName, level: 'error', text: line });
    };

    proc.on('exit', (code) => {
      this.status[coreName] = 'crashed';
      this.emit('core-status', { core: coreName, status: 'crashed', code });
      this.emit('log', { level: 'error', text: `${coreName} crashed with code ${code}` });
    });

    proc.stdout.on('data', stdoutHandler);
    proc.stderr.on('data', stderrHandler);

    this.emit('log', { level: 'info', text: `Started ${coreName} (PID: ${proc.pid})` });
  }

  async waitForCoreReady(coreName, timeoutMs) {
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        reject(new Error(`${coreName} failed to become ready within ${timeoutMs}ms`));
      }, timeoutMs);

      const handler = ({ core, status }) => {
        if (core === coreName && status === 'running') {
          clearTimeout(timeout);
          this.removeListener('core-status', handler);
          resolve();
        }
      };

      this.on('core-status', handler);
    });
  }

  stopCore(coreName) {
    const proc = this.processes.get(coreName);
    if (proc && !proc.killed) {
      this.emit('log', { level: 'info', text: `Terminating ${coreName} (PID: ${proc.pid})` });
      proc.kill('SIGTERM');
    }
    this.processes.delete(coreName);
    this.status[coreName] = 'stopped';
  }

  async restartCore(coreName) {
    this.stopCore(coreName);
    await this.startCore(coreName);
    await this.waitForCoreReady(coreName, 15000);
  }

  stopAll() {
    this.emit('log', { level: 'info', text: 'Stopping all cores...' });
    for (const core of Array.from(this.processes.keys())) {
      this.stopCore(core);
    }
  }

  getSystemStatus() {
    return {
      cores: { ...this.status },
      healthy: Object.values(this.status).every((s) => s === 'running'),
      timestamp: Date.now(),
    };
  }
}

module.exports = { CALILauncher };
