
/**
 * orb-bridge.js — UPDATED status emission
 * 
 * The bridge now receives the new four-layer state from Python
 * and emits structured events to the renderer.
 * 
 * Key changes:
 *   - Status includes source + timestamp on every field
 *   - Motion includes target + completion event
 *   - Commands include full lifecycle
 *   - Block reasons are explicit (not just false booleans)
 */

const { spawn } = require('child_process');
const path = require('path');

class OrbBridge {
  constructor(ps1Path) {
    this.ps1Path = ps1Path;
    this.process = null;
    this.listeners = new Map();
    this.commandLedger = new Map(); // request_id → lifecycle
  }

  start() {
    this.process = spawn('powershell.exe', [
      '-ExecutionPolicy', 'Bypass',
      '-File', this.ps1Path
    ], {
      stdio: ['pipe', 'pipe', 'pipe']
    });

    // Handle stdout (JSONL from Python)
    let buffer = '';
    this.process.stdout.on('data', (data) => {
      buffer += data.toString('utf-8');
      const lines = buffer.split('\n');
      buffer = lines.pop(); // Keep incomplete line

      for (const line of lines) {
        if (line.trim()) this._handlePythonMessage(line.trim());
      }
    });

    this.process.stderr.on('data', (data) => {
      console.error('[ORB Bridge STDERR]', data.toString('utf-8'));
    });

    this.process.on('close', (code) => {
      console.log(`[ORB Bridge] Python process exited with code ${code}`);
      this.emit('orb_disconnected', { code });
    });
  }

  _handlePythonMessage(line) {
    try {
      const msg = JSON.parse(line);

      switch (msg.type) {
        case 'orb_ready':
          this.emit('orb_ready', msg);
          break;

        case 'command_accepted':
          this.commandLedger.set(msg.request_id, {
            phase: 'ACCEPTED',
            acceptedAt: Date.now(),
            commandType: msg.command_type
          });
          this.emit('command_accepted', msg);
          break;

        case 'command_completed':
          this._updateCommandLifecycle(msg.request_id, 'COMPLETED', msg.result);
          this.emit('command_completed', msg);
          break;

        case 'command_failed':
          this._updateCommandLifecycle(msg.request_id, 'FAILED', null, msg.error);
          this.emit('command_failed', msg);
          break;

        case 'command_timeout':
          this._updateCommandLifecycle(msg.request_id, 'TIMEOUT', null, 
            `Timed out after ${msg.timeout_seconds}s`);
          this.emit('command_timeout', msg);
          break;

        case 'status_update':
          // New structured status with full provenance
          this.emit('orb_status_change', this._enrichStatus(msg.status));
          break;

        default:
          this.emit('orb_message', msg);
      }
    } catch (e) {
      console.error('[ORB Bridge] Failed to parse Python message:', e);
      console.error('Raw line:', line.substring(0, 200));
    }
  }

  _updateCommandLifecycle(requestId, phase, result, error) {
    const entry = this.commandLedger.get(requestId);
    if (entry) {
      entry.phase = phase;
      entry.completedAt = Date.now();
      entry.result = result;
      entry.error = error;
      entry.duration = entry.completedAt - entry.acceptedAt;
    }
  }

  /**
   * Enrich status with renderer-friendly fields.
   * Converts the four-layer state into what FloatingOrb.jsx expects.
   */
  _enrichStatus(status) {
    const listening = status.listening_mode || {};
    const motion = status.motion_status || {};

    return {
      // Listening — now with block reason, not just false
      listening: {
        enabled: listening.enabled,
        canListen: listening.enabled, // effective state
        wantListen: listening.want_listen, // desired state
        micAvailable: listening.mic_available,
        cp3Ready: listening.cp3_ready,
        blockReason: listening.block_reason,     // ← NEW: why it failed
        blockSource: listening.block_source,     // ← NEW: who reported it
        blockCheckedAt: listening.block_checked_at, // ← NEW: when
      },

      // Motion — now with target + completion
      motion: {
        enabled: motion.enabled,
        target: motion.target,                    // ← NEW: where it's going
        targetPosition: motion.target_position,   // ← NEW: coordinates
        startedAt: motion.started_at,
        completedAt: motion.completed_at,
        result: motion.result,                    // ← NEW: success/blocked/timeout
      },

      // Voice
      voice: {
        enabled: status.voice_status?.enabled,
        ttsReady: status.voice_status?.tts_ready,
      },

      // Cognition
      cognition: {
        enabled: status.cognition_status?.enabled,
        llmReady: status.cognition_status?.llm_ready,
      },

      // System
      system: {
        alive: status.system_status?.orb_alive,
        checkoutPath: status.system_status?.checkout_path,
      },

      // Commands
      commands: {
        active: status.command_status?.active_commands || 0,
        lastCommand: status.command_status?.last_command,
        ledger: Array.from(this.commandLedger.entries())
          .slice(-5)
          .map(([id, entry]) => ({ id, ...entry }))
      }
    };
  }

  // Send command to Python with lifecycle tracking
  sendCommand(type, payload = {}) {
    const requestId = `req_${Date.now()}_${Math.random().toString(36).substr(2, 5)}`;
    const command = {
      type,
      request_id: requestId,
      timestamp: Date.now(),
      ...payload
    };

    this.process.stdin.write(JSON.stringify(command) + '\n');
    return requestId; // Caller can track this request_id
  }

  // Convenience methods
  setListening(enabled) {
    return this.sendCommand('set_listening', { enabled });
  }

  setMotion(target, position = null) {
    return this.sendCommand('set_motion', { target, position });
  }

  getStatus() {
    return this.sendCommand('get_status');
  }

  getFullStatus() {
    return this.sendCommand('get_full_status');
  }

  diagnose(domain = 'listening') {
    return this.sendCommand('diagnose', { domain });
  }

  emit(event, data) {
    const callbacks = this.listeners.get(event) || [];
    callbacks.forEach(cb => {
      try { cb(data); } catch (e) { console.error(e); }
    });
  }

  on(event, callback) {
    if (!this.listeners.has(event)) this.listeners.set(event, []);
    this.listeners.get(event).push(callback);
  }

  off(event, callback) {
    const callbacks = this.listeners.get(event) || [];
    const idx = callbacks.indexOf(callback);
    if (idx > -1) callbacks.splice(idx, 1);
  }

  shutdown() {
    this.sendCommand('shutdown');
    setTimeout(() => {
      if (this.process && !this.process.killed) {
        this.process.kill();
      }
    }, 2000);
  }
}

module.exports = { OrbBridge };
