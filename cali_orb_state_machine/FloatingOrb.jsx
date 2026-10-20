
import React, { useState, useEffect, useRef, useCallback } from 'react';
import './FloatingOrb.css';

/**
 * FloatingOrb.jsx — CALI Orb Renderer (State Machine v3.5)
 * 
 * Consumes the new four-layer state format from the bridge:
 *   - listening: enabled, canListen, wantListen, micAvailable, cp3Ready,
 *                blockReason, blockSource, blockCheckedAt
 *   - motion: enabled, target, targetPosition, startedAt, completedAt, result
 *   - voice: enabled, ttsReady
 *   - cognition: enabled, llmReady
 *   - commands: active, lastCommand, ledger
 *   - system: alive, checkoutPath
 */

const FloatingOrb = () => {
  // ── Core State ──
  const [orbReady, setOrbReady] = useState(false);
  const [status, setStatus] = useState({});
  const [commandLog, setCommandLog] = useState([]);
  const [showDebug, setShowDebug] = useState(false);

  // ── Listening State ──
  const [listening, setListening] = useState(false);
  const [listenBlockReason, setListenBlockReason] = useState(null);
  const [listenBlockSource, setListenBlockSource] = useState(null);

  // ── Motion State ──
  const [motionTarget, setMotionTarget] = useState('idle');
  const [motionResult, setMotionResult] = useState(null);
  const [motionInProgress, setMotionInProgress] = useState(false);

  // ── Voice State ──
  const [speaking, setSpeaking] = useState(false);

  // ── Cognition State ──
  const [cognating, setCognating] = useState(false);

  // ── Position ──
  const [position, setPosition] = useState({ x: 100, y: 100 });
  const orbRef = useRef(null);
  const dragOffset = useRef({ x: 0, y: 0 });
  const isDragging = useRef(false);

  // ── Bridge Setup ──
  useEffect(() => {
    if (!window.electronAPI) {
      console.error('[FloatingOrb] electronAPI not available');
      return;
    }

    // Orb ready handshake
    window.electronAPI.onOrbStatusChange((data) => {
      if (data.type === 'orb_ready') {
        setOrbReady(true);
        console.log('[FloatingOrb] ORB ready:', data);
      }
    });

    // Status updates (new four-layer format)
    window.electronAPI.onOrbStatusChange((data) => {
      if (data.type === 'status_update' || data.listening) {
        handleStatusUpdate(data);
      }
    });

    // Command lifecycle events
    window.electronAPI.onOrbStatusChange((data) => {
      if (data.type?.startsWith('command_')) {
        logCommand(data);
      }
    });

    // Speech pulse (TTS speaking)
    window.electronAPI.onSpeechPulse((speaking) => {
      setSpeaking(speaking);
    });

    // Cognitive pulse
    window.electronAPI.onCognitivePulse((active) => {
      setCognating(active);
    });

    // Request initial status
    window.electronAPI.getOrbStatus();

    return () => {
      // Cleanup listeners if needed
    };
  }, []);

  // ── Status Update Handler ──
  const handleStatusUpdate = useCallback((data) => {
    setStatus(data);

    // Listening
    if (data.listening) {
      const l = data.listening;
      setListening(l.enabled && l.canListen);
      setListenBlockReason(l.blockReason);
      setListenBlockSource(l.blockSource);
    }

    // Motion
    if (data.motion) {
      const m = data.motion;
      setMotionTarget(m.target || 'idle');
      setMotionResult(m.result);
      setMotionInProgress(m.enabled && !m.completedAt && m.startedAt);
    }

    // Voice
    if (data.voice) {
      // voice state handled by speech pulse
    }

    // Cognition
    if (data.cognition) {
      // cognition state handled by cognitive pulse
    }
  }, []);

  // ── Command Logging ──
  const logCommand = useCallback((data) => {
    setCommandLog(prev => {
      const entry = {
        id: data.request_id || `cmd_${Date.now()}`,
        type: data.type,
        commandType: data.command_type,
        timestamp: Date.now(),
        result: data.result,
        error: data.error,
      };
      const updated = [entry, ...prev].slice(0, 50);
      return updated;
    });
  }, []);

  // ── Toggle Handlers ──
  const handleListenToggle = useCallback(() => {
    const newState = !listening;

    // Optimistic UI: show toggle moving, wait for bridge confirmation
    // The bridge will emit status_update with the real effective state

    if (window.electronAPI?.setListening) {
      window.electronAPI.setListening(newState);
    } else if (window.electronAPI?.orbQuery) {
      // Fallback: send raw command
      window.electronAPI.orbQuery('set_listening', { enabled: newState });
    }
  }, [listening]);

  const handleMotionTarget = useCallback((target, position = null) => {
    if (window.electronAPI?.orbQuery) {
      window.electronAPI.orbQuery('set_motion', { target, position });
    }
  }, []);

  const handleSpeak = useCallback((text) => {
    if (window.electronAPI?.orbSpeak) {
      window.electronAPI.orbSpeak(text);
    } else if (window.electronAPI?.orbQuery) {
      window.electronAPI.orbQuery('orb_speak', { text });
    }
  }, []);

  const handleDiagnose = useCallback((domain = 'listening') => {
    if (window.electronAPI?.orbQuery) {
      window.electronAPI.orbQuery('diagnose', { domain });
    }
  }, []);

  // ── Drag Handling ──
  const handleMouseDown = useCallback((e) => {
    isDragging.current = true;
    dragOffset.current = {
      x: e.clientX - position.x,
      y: e.clientY - position.y,
    };
  }, [position]);

  const handleMouseMove = useCallback((e) => {
    if (!isDragging.current) return;
    setPosition({
      x: e.clientX - dragOffset.current.x,
      y: e.clientY - dragOffset.current.y,
    });
  }, []);

  const handleMouseUp = useCallback(() => {
    isDragging.current = false;
  }, []);

  useEffect(() => {
    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [handleMouseMove, handleMouseUp]);

  // ── Render ──
  return (
    <div className="floating-orb-container">
      {/* Main Orb */}
      <div
        ref={orbRef}
        className={`floating-orb
          ${orbReady ? 'orb-ready' : 'orb-loading'}
          ${listening ? 'orb-listening' : ''}
          ${speaking ? 'orb-speaking' : ''}
          ${cognating ? 'orb-cognating' : ''}
          ${motionInProgress ? 'orb-moving' : ''}
        `}
        style={{
          left: position.x,
          top: position.y,
        }}
        onMouseDown={handleMouseDown}
      >
        {/* Orb Core */}
        <div className="orb-core">
          <div className={`orb-pulse ${listening ? 'pulse-active' : ''}`} />
          <div className={`orb-glow ${speaking ? 'glow-speaking' : ''}`} />
          <div className={`orb-ring ${cognating ? 'ring-cognating' : ''}`} />
        </div>

        {/* Status Indicators */}
        <div className="orb-status-indicators">
          {listening && <span className="indicator indicator-listening" title="Listening" />}
          {speaking && <span className="indicator indicator-speaking" title="Speaking" />}
          {cognating && <span className="indicator indicator-cognating" title="Thinking" />}
          {motionInProgress && (
            <span className="indicator indicator-moving" title={`Moving to ${motionTarget}`} />
          )}
        </div>

        {/* Block Reason Tooltip */}
        {listenBlockReason && (
          <div className="orb-block-tooltip">
            <div className="block-icon">⚠️</div>
            <div className="block-text">
              <div className="block-reason">{listenBlockReason}</div>
              <div className="block-source">via {listenBlockSource}</div>
            </div>
          </div>
        )}
      </div>

      {/* Control Panel */}
      <div className="orb-control-panel">
        <h3>CALI Orb Controls</h3>

        {/* Listening Toggle */}
        <div className="control-row">
          <label className="toggle-label">
            <input
              type="checkbox"
              checked={listening}
              onChange={handleListenToggle}
            />
            <span className="toggle-slider" />
            <span className="toggle-text">
              Listening
              {listenBlockReason && (
                <span className="toggle-blocked" title={listenBlockReason}>
                  {' '}⚠️
                </span>
              )}
            </span>
          </label>
          {listenBlockReason && (
            <div className="block-detail">
              Blocked: {listenBlockReason} (reported by {listenBlockSource})
            </div>
          )}
        </div>

        {/* Motion Controls */}
        <div className="control-row">
          <span className="control-label">Motion Target:</span>
          <div className="motion-buttons">
            {['idle', 'cursor', 'dock'].map(target => (
              <button
                key={target}
                className={`motion-btn ${motionTarget === target ? 'active' : ''}`}
                onClick={() => handleMotionTarget(target)}
              >
                {target}
              </button>
            ))}
          </div>
          {motionResult && (
            <div className="motion-result">
              Last: {motionResult}
              {motionInProgress && <span className="motion-in-progress"> (in progress...)</span>}
            </div>
          )}
        </div>

        {/* Quick Speak */}
        <div className="control-row">
          <input
            type="text"
            className="speak-input"
            placeholder="Say something..."
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                handleSpeak(e.target.value);
                e.target.value = '';
              }
            }}
          />
        </div>

        {/* Diagnostics */}
        <div className="control-row">
          <button className="diag-btn" onClick={() => handleDiagnose('listening')}>
            Diagnose Listening
          </button>
          <button className="diag-btn" onClick={() => handleDiagnose('command')}>
            Diagnose Commands
          </button>
        </div>

        {/* Debug Toggle */}
        <div className="control-row">
          <button className="debug-toggle" onClick={() => setShowDebug(!showDebug)}>
            {showDebug ? 'Hide' : 'Show'} Debug
          </button>
        </div>

        {/* Debug Panel */}
        {showDebug && (
          <div className="debug-panel">
            <h4>System Status</h4>
            <pre className="debug-pre">{JSON.stringify(status, null, 2)}</pre>

            <h4>Command Ledger (last 10)</h4>
            <div className="command-log">
              {commandLog.slice(0, 10).map(cmd => (
                <div key={cmd.id} className={`command-entry command-${cmd.type}`}>
                  <span className="cmd-time">
                    {new Date(cmd.timestamp).toLocaleTimeString()}
                  </span>
                  <span className="cmd-type">{cmd.commandType || cmd.type}</span>
                  {cmd.error && <span className="cmd-error">❌ {cmd.error}</span>}
                  {cmd.result && <span className="cmd-ok">✅</span>}
                </div>
              ))}
            </div>

            <h4>Checkout Path</h4>
            <div className="checkout-path">
              {status.system?.checkoutPath || 'Unknown'}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default FloatingOrb;
