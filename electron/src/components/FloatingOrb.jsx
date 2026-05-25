// src/components/FloatingOrb.jsx - Optimized with Lerp
import React, { useState, useEffect, useRef, useCallback } from 'react';
import './FloatingOrb.css';

const LOGIC_MODE_VISUALS = {
  deductive: { label: 'Deductive', color: '#59b7ff' },
  inductive: { label: 'Inductive', color: '#58d68d' },
  intuitive: { label: 'Intuitive', color: '#f4c95d' }
};

function mapCognitiveModeToVisual(cognitiveMode) {
  const mode = String(cognitiveMode || '').toUpperCase();
  if (mode.includes('INTUITION')) return 'intuitive';
  if (mode.includes('HABIT')) return 'inductive';
  return 'deductive';
}

const FloatingOrb = ({ workerId = "CALI_UNIT_01" }) => {
  const [position, setPosition] = useState(() => ({ x: window.innerWidth / 2, y: window.innerHeight / 2 }));
  const [targetPos, setTargetPos] = useState(() => ({ x: window.innerWidth / 2, y: window.innerHeight / 2 }));
  const [isMoving, setIsMoving] = useState(false);
  const [animationMode, setAnimationMode] = useState('idle'); // idle, avoiding, assisting, learning
  const [orbSize, setOrbSize] = useState(1.0); // multiplier for size
  const [orbSpeed, setOrbSpeed] = useState(0.05); // lerp factor
  const [orbColor, setOrbColor] = useState(LOGIC_MODE_VISUALS.deductive.color);
  const [mood, setMood] = useState(0.75); // 0-1 scale for orb health/color
  const [logicMode, setLogicMode] = useState('deductive');
  const [bridgeStatus, setBridgeStatus] = useState('Python link booting');
  const [bloomLevel, setBloomLevel] = useState(0);
  const [statusTone, setStatusTone] = useState('Observing');

  // Calculate mood based on activity
  const updateMood = useCallback(() => {
    let newMood = 0.75;

    if (animationMode === 'assisting') newMood += 0.15;
    if (animationMode === 'avoiding') newMood -= 0.1;
    if (isMoving) newMood += 0.05;

    // Idle time factor (simplified)
    const idleTime = Date.now() - (lastActivityRef.current || Date.now());
    if (idleTime > 15000) newMood += 0.1;

    newMood = Math.max(0, Math.min(1, newMood));
    setMood(newMood);
  }, [animationMode, isMoving]);

  const lastActivityRef = useRef(Date.now());

  // Color based on mood/health
  const getOrbColor = (mood) => {
    if (mood >= 0.8) return '#2dd4ff'; // Bright blue - healthy
    if (mood >= 0.6) return '#facc15'; // Yellow - warning
    return '#f87171'; // Red - unhealthy
  };

  // Convert hex to rgb
  const hexToRgb = (hex) => {
    const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
    return result ? {
      r: parseInt(result[1], 16),
      g: parseInt(result[2], 16),
      b: parseInt(result[3], 16)
    } : null;
  };

  // Update mood periodically
  useEffect(() => {
    const interval = setInterval(updateMood, 1000);
    return () => clearInterval(interval);
  }, [updateMood]);

  // Refs for animation loop
  const positionRef = useRef(position);
  const targetRef = useRef(targetPos);
  const lerpFactorRef = useRef(orbSpeed); // Smoothness factor (learnable!)
  const frameCountRef = useRef(0);

  // Connect to UCM backend
  const wsRef = useRef(null);

  useEffect(() => {
    positionRef.current = position;
  }, [position]);

  useEffect(() => {
    targetRef.current = targetPos;
  }, [targetPos]);

  useEffect(() => {
    lerpFactorRef.current = orbSpeed;
  }, [orbSpeed]);

  useEffect(() => {
    if (bloomLevel <= 0) {
      return undefined;
    }

    const decay = setInterval(() => {
      setBloomLevel((current) => Math.max(0, current - 0.08));
    }, 120);

    return () => clearInterval(decay);
  }, [bloomLevel]);

  // ✅ SAFE: Listen for cursor movement (not screen capture)
  useEffect(() => {
    const handleMouseMove = (e) => {
      lastActivityRef.current = Date.now(); // Update activity timestamp

      // Update target position based on cursor
      const cursorX = e.clientX;
      const cursorY = e.clientY;

      // Calculate avoidance vector
      const dx = cursorX - positionRef.current.x;
      const dy = cursorY - positionRef.current.y;
      const distance = Math.sqrt(dx * dx + dy * dy);

      const avoidanceDistance = 350; // pixels

      if (distance < avoidanceDistance) {
        // Cursor is too close - calculate avoidance target
        const angle = Math.atan2(dy, dx);
        const avoidDistance = avoidanceDistance * 1.3; // Extra buffer

        let newTargetX = cursorX + Math.cos(angle) * avoidDistance;
        let newTargetY = cursorY + Math.sin(angle) * avoidDistance;

        // Clamp to viewport
        newTargetX = Math.max(50, Math.min(window.innerWidth - 50, newTargetX));
        newTargetY = Math.max(50, Math.min(window.innerHeight - 50, newTargetY));

        setTargetPos({ x: newTargetX, y: newTargetY });
        setIsMoving(true);
        setAnimationMode('avoiding');

        // Send movement pattern to SKG for learning
        if (frameCountRef.current % 30 === 0) { // Sample every 30 frames
          if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify({
              action: 'learn_movement',
              pattern: {
                from: positionRef.current,
                to: { x: newTargetX, y: newTargetY },
                cursor_distance: distance,
                velocity: lerpFactorRef.current,
                timestamp: Date.now()
              }
            }));
          }
        }
      } else if (distance > avoidanceDistance * 1.5) {
        // Cursor is far away - gentle floating behavior
        const time = Date.now() * 0.001; // Convert to seconds
        const floatRadius = 100;
        const centerX = window.innerWidth / 2;
        const centerY = window.innerHeight / 2;

        // Gentle floating motion
        const floatX = centerX + Math.sin(time * 0.5) * floatRadius;
        const floatY = centerY + Math.cos(time * 0.3) * floatRadius * 0.5;

        setTargetPos({ x: floatX, y: floatY });
        setAnimationMode('idle');
      }

      frameCountRef.current++;

      if (window.electronAPI && frameCountRef.current % 4 === 0) {
        window.electronAPI.orbCursorMove(cursorX, cursorY).catch(() => {});
      }
    };

    window.addEventListener('mousemove', handleMouseMove);
    return () => window.removeEventListener('mousemove', handleMouseMove);
  }, []);

  useEffect(() => {
    if (!window.electronAPI) {
      return undefined;
    }

    const applyLogicVisual = (pulse = {}) => {
      const nextLogicMode = mapCognitiveModeToVisual(pulse.cognitive_mode);
      const nextColor = LOGIC_MODE_VISUALS[nextLogicMode].color;
      const intensity = Math.max(0.2, Math.min(1, pulse.glow_intensity ?? 0.45));

      setLogicMode(nextLogicMode);
      setOrbColor(nextColor);
      setBridgeStatus(`${LOGIC_MODE_VISUALS[nextLogicMode].label} channel live`);
      setBloomLevel((current) => Math.max(current, intensity));
      setStatusTone(
        nextLogicMode === 'intuitive'
          ? 'Pattern lock'
          : nextLogicMode === 'inductive'
            ? 'Learning drift'
            : 'Logic guard'
      );
    };

    const unsubscribers = [];

    unsubscribers.push(window.electronAPI.onCognitivePulse((_event, pulse) => {
      applyLogicVisual(pulse);
    }));

    unsubscribers.push(window.electronAPI.onSpeechPulse((_event, message) => {
      applyLogicVisual(message?.data || {});
      setAnimationMode('assisting');
      setBridgeStatus('Speech pulse received');
      setStatusTone('Listening');
    }));

    unsubscribers.push(window.electronAPI.onOrbStatusChange((_event, status) => {
      if (status?.controller_status) {
        setBridgeStatus(`Brain ${status.controller_status}`);
      }
    }));

    unsubscribers.push(window.electronAPI.onOrbBridgeMessage((_event, message) => {
      if (message?.type === 'ready') {
        setBridgeStatus('Python bridge ready');
        setBloomLevel((current) => Math.max(current, 0.55));
        setStatusTone('Present');
      } else if (message?.type === 'bridge_exit') {
        setBridgeStatus('Python bridge offline');
        setStatusTone('Sleeping');
      }
    }));

    unsubscribers.push(window.electronAPI.onHysteresis((_event, data) => {
      setBloomLevel(1);
      setBridgeStatus(`Hysteresis ${data.triggerThreshold} -> ${data.releaseThreshold}`);
      setAnimationMode('assisting');
      setStatusTone('Bloom threshold');
      setTimeout(() => setAnimationMode('idle'), 800);
    }));

    unsubscribers.push(window.electronAPI.onVerbalCommand((_event, message) => {
      if (message?.command === 'change_color' && message.color) setOrbColor(message.color);
      if (message?.command === 'increase_size') setOrbSize((size) => Math.min(size + 0.1, 1.6));
      if (message?.command === 'decrease_size') setOrbSize((size) => Math.max(size - 0.1, 0.7));
      if (message?.command === 'speed_up') setOrbSpeed((speed) => Math.min(speed + 0.02, 0.2));
      if (message?.command === 'slow_down') setOrbSpeed((speed) => Math.max(speed - 0.02, 0.02));
    }));

    window.electronAPI.getOrbStatus?.().catch(() => {});
    return () => {
      unsubscribers.forEach((unsubscribe) => {
        if (typeof unsubscribe === 'function') {
          unsubscribe();
        }
      });
    };
  }, []);

  // Listen for settings updates
  useEffect(() => {
    if (window.electronAPI) {
      const handleSettingsUpdate = (event, settings) => {
        console.log('⚙️ Settings update:', settings);
        
        if (settings.color) setOrbColor(settings.color);
        if (settings.size) setOrbSize(settings.size);
        if (settings.speed) setOrbSpeed(settings.speed);
        // pulse could be used for animation timing if implemented
      };

      const handleOpenSettings = () => {
        // Send IPC to main process to open settings window
        if (window.electronAPI) {
          window.electronAPI.openSettings();
        }
      };

      window.electronAPI.onSettingsUpdate(handleSettingsUpdate);
      window.electronAPI.onOpenSettings(handleOpenSettings);

      return () => {
        // Clean up if needed
      };
    }
  }, []);

  // 🎮 LERP ANIMATION LOOP
  useEffect(() => {
    let rafId;

    const lerp = (start, end, factor) => {
      return start + (end - start) * factor;
    };

    const animate = () => {
      const current = positionRef.current;
      let target = targetRef.current;

      // Update idle floating target continuously
      if (animationMode === 'idle') {
        const time = Date.now() * 0.001; // Convert to seconds
        const floatRadius = 100;
        const centerX = window.innerWidth / 2;
        const centerY = window.innerHeight / 2;

        // Gentle floating motion
        const floatX = centerX + Math.sin(time * 0.5) * floatRadius;
        const floatY = centerY + Math.cos(time * 0.3) * floatRadius * 0.5;

        target = { x: floatX, y: floatY };
        targetRef.current = target; // Update ref so it's consistent
      }

      // Dynamic lerp factor based on animation mode
      let factor = lerpFactorRef.current;
      if (animationMode === 'avoiding') factor = 0.15; // Faster avoidance
      if (animationMode === 'assisting') factor = 0.08; // Slower, intentional movement

      const newX = lerp(current.x, target.x, factor);
      const newY = lerp(current.y, target.y, factor);

      // Check if movement is complete (within 5px) - but for idle, never complete since target moves
      const distanceToTarget = Math.sqrt(
        (target.x - newX) ** 2 + (target.y - newY) ** 2
      );

      if (distanceToTarget < 5 && animationMode !== 'idle') {
        setIsMoving(false);
        if (animationMode === 'avoiding') {
          setAnimationMode('idle');
        }
      } else {
        setIsMoving(true);
      }

      // Only update position if there's actual movement
      if (Math.abs(newX - current.x) > 0.1 || Math.abs(newY - current.y) > 0.1) {
        setPosition({ x: newX, y: newY });
      }

      rafId = requestAnimationFrame(animate);
    };

    console.log('🎮 Starting animation loop');
    rafId = requestAnimationFrame(animate);
    return () => {
      console.log('🛑 Stopping animation loop');
      cancelAnimationFrame(rafId);
    };
  }, [animationMode]);

  // WebSocket connection to UCM for SKG learning
  useEffect(() => {
    console.log('🔌 Attempting to connect to orb server...');

    const connectWebSocket = () => {
      try {
        // Orb_Assistant is not a worker.
        // It uses a dedicated ORB channel and handshake.
        // Do not reuse worker logic.
        const ws = new WebSocket(`ws://localhost:8000/ws/orb_assistant`);
        wsRef.current = ws;

        ws.onopen = () => {
          console.log('✅ Orb connected to UCM SKG server - Sending Handshake');
          ws.send(JSON.stringify({
            type: "ORB_HANDSHAKE",
            orb_id: "ORB_ASSISTANT_PRIMARY_V1",
            role: "orb",
            capabilities: ["presence", "mediation", "ui"]
          }));
        };

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            console.log('📨 Received WS message:', data);

            // Update lerp factor based on learned preferences
            if (data.type === 'lerp_optimization') {
              lerpFactorRef.current = data.optimal_velocity;
              console.log('🎯 Updated lerp factor:', lerpFactorRef.current);
            }

            // ECM-driven drift target (e.g., user prefers orb on right side)
            if (data.type === 'drift_preference') {
              const { preferred_quadrant } = data;
              const centerX = window.innerWidth / 2;
              const centerY = window.innerHeight / 2;

              const quadrantTargets = {
                'top_left': { x: centerX - 200, y: centerY - 200 },
                'top_right': { x: centerX + 200, y: centerY - 200 },
                'bottom_left': { x: centerX - 200, y: centerY + 200 },
                'bottom_right': { x: centerX + 200, y: centerY + 200 },
                'center': { x: centerX, y: centerY }
              };

              const newTarget = quadrantTargets[preferred_quadrant] || quadrantTargets['center'];
              setTargetPos(newTarget);
              console.log('🎯 Updated drift target:', newTarget);
            }
          } catch (error) {
            console.error('❌ Error parsing WS message:', error);
          }
        };

        ws.onclose = (event) => {
          console.log('🔌 WebSocket closed:', event.code, event.reason);
          // Attempt to reconnect after 5 seconds
          setTimeout(connectWebSocket, 5000);
        };

        ws.onerror = (error) => {
          console.error('❌ WebSocket error:', error);
        };

      } catch (error) {
        console.error('❌ Failed to create WebSocket:', error);
        // Retry connection
        setTimeout(connectWebSocket, 5000);
      }
    };

    connectWebSocket();

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  const handleOrbClick = async () => {
    lastActivityRef.current = Date.now(); // Update activity timestamp
    setAnimationMode('assisting');

    // User explicitly clicked orb - VOLUNTARY interaction
    wsRef.current?.send(JSON.stringify({
      action: 'voluntary_interaction',
      type: 'orb_click',
      timestamp: Date.now()
    }));

    // Query mode
    setTimeout(() => setAnimationMode('idle'), 2000);
  };

  const visualLabel = LOGIC_MODE_VISUALS[logicMode].label;
  const bloomScale = 1 + bloomLevel * 0.2;
  const bloomShadow = 30 + bloomLevel * 70;
  const auraOpacity = 0.25 + bloomLevel * 0.55;
  const shellOpacity = 0.34 + bloomLevel * 0.22;

  return (
    <>
      <div
        className={`floating-orb ${animationMode} logic-${logicMode} ${bloomLevel > 0.2 ? 'blooming' : ''}`}
        style={{
          position: 'fixed',
          left: `${position.x - 75 * orbSize}px`,
          top: `${position.y - 75 * orbSize}px`,
          transform: `scale(${(isMoving ? 1.05 : 1) * bloomScale})`,
          transition: 'transform 0.1s ease-out',
          pointerEvents: 'auto',
          opacity: 0.88 + bloomLevel * 0.12
        }}
        onClick={handleOrbClick}
        onMouseEnter={() => {
          if (window.electronAPI) {
             window.electronAPI.setIgnoreMouseEvents(false);
          }
        }}
        onMouseLeave={() => {
          if (window.electronAPI) {
             window.electronAPI.setIgnoreMouseEvents(true, { forward: true });
          }
        }}
      >
        <div className="orb-visual" style={{ transform: `scale(${orbSize})` }}>
          <div 
            className={`orb-core ${animationMode}`} 
            style={{
              background: `radial-gradient(circle, ${orbColor}, #1a1a2e)`,
              boxShadow: `0 0 ${bloomShadow}px ${orbColor}, inset 0 0 ${20 + bloomLevel * 25}px ${orbColor}`,
              opacity: 0.86 + bloomLevel * 0.14
            }}
          />
          <div 
            className={`orb-aura ${animationMode}`}
            style={{
              background: `radial-gradient(circle, ${orbColor}88, transparent)`,
              opacity: auraOpacity
            }}
          />
        </div>
        <div
          className="orb-cockpit"
          style={{
            background: `linear-gradient(180deg, ${orbColor}22, rgba(6, 10, 18, ${shellOpacity}))`,
            borderColor: `${orbColor}66`,
            boxShadow: `0 14px 42px ${orbColor}22`
          }}
        >
          <div className="orb-cockpit-kicker">Caleon</div>
          <div className="orb-cockpit-title">{statusTone}</div>
          <div className="orb-cockpit-row">
            <span className="orb-mode-pill" style={{ borderColor: `${orbColor}99`, color: orbColor }}>
              {visualLabel}
            </span>
            <span className="orb-cockpit-status">{bridgeStatus}</span>
          </div>
        </div>
      </div>
    </>
  );
};

export default FloatingOrb;
