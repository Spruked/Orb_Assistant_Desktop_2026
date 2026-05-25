import React, { useEffect, useRef, useState } from 'react';
import './LivingOrb.css';

const colorForHealth = (health) => {
  if (health >= 0.8) return 'var(--orb-color-good)';
  if (health >= 0.6) return 'var(--orb-color-warn)';
  return 'var(--orb-color-bad)';
};

const resolveBridgeUrl = (fallbackUrl) => {
  if (typeof window === 'undefined') return fallbackUrl;
  const plugin = window.UCM_4_Core;
  if (plugin && (plugin.bridgeUrl || plugin.ws)) {
    return plugin.bridgeUrl || plugin.ws;
  }
  return fallbackUrl;
};

const LivingOrb = ({ bridgeUrl = 'ws://localhost:9876' }) => {
  const wsRef = useRef(null);
  const reconnectRef = useRef(null);
  const [resolvedBridgeUrl, setResolvedBridgeUrl] = useState(bridgeUrl);
  const [health, setHealth] = useState(1.0);
  const [isListening, setIsListening] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [statusLine, setStatusLine] = useState('Initializing CALI...');
  const [lastText, setLastText] = useState('');
  const [permissions, setPermissions] = useState({
    desktop: true,
    browser: true,
    voice: true,
    listening: true,
  });
  const [cognitiveMode, setCognitiveMode] = useState('GUARD');
  const [glowIntensity, setGlowIntensity] = useState(0.5);

  // --- speech synthesis helper ---
  const speak = (text) => {
    if (typeof window === 'undefined' || !window.speechSynthesis) return;
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 0.95;
    utterance.pitch = 1.05;
    utterance.onstart = () => setIsSpeaking(true);
    utterance.onend = () => setIsSpeaking(false);
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(utterance);
  };

  // --- mouse tracking for cognitive processing ---
  useEffect(() => {
    const handleMouseMove = (event) => {
      if (window.electronAPI) {
        window.electronAPI.orbCursorMove(event.clientX, event.clientY);
      }
    };

    document.addEventListener('mousemove', handleMouseMove);
    return () => document.removeEventListener('mousemove', handleMouseMove);
  }, []);

  // --- electron API connection ---
  useEffect(() => {
    if (window.electronAPI) {
      // Listen for cognitive pulses
      window.electronAPI.onCognitivePulse((event, pulse) => {
        if (pulse) {
          setGlowIntensity(pulse.glow_intensity || 0.5);
          setCognitiveMode(pulse.cognitive_mode || 'GUARD');
          setHealth(pulse.glow_intensity || 1.0);
          setStatusLine(`Mode: ${pulse.cognitive_mode || 'GUARD'}`);
        }
      });

      setStatusLine('Orb linked to CALI bridge');
      setIsListening(true);
    } else {
      setStatusLine('Electron API not available');
    }

    return () => {
      if (window.electronAPI) {
        // Clean up listeners if needed
      }
    };
  }, []);

  const handleClick = async () => {
    const promptText = window.prompt('Ask CALI:', lastText || '');
    if (!promptText) return;
    if (window.electronAPI) {
      try {
        const result = await window.electronAPI.orbQuery(promptText);
        setLastText(result?.echo || 'Response received');
        setStatusLine('Query processed');
        if (result?.cognitive_result?.glow_intensity > 0.75) {
          speak(result.echo);
        }
      } catch (err) {
        console.error('Query error:', err);
        setStatusLine('Query failed');
      }
    }
  };

  const togglePermission = (key) => {
    setPermissions((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const color = colorForHealth(health);
  const coreClasses = ['living-orb-core'];
  if (isListening) coreClasses.push('listening');
  if (isSpeaking) coreClasses.push('speaking');
  if (cognitiveMode === 'INTUITION-JUMP') coreClasses.push('jumping');
  if (cognitiveMode === 'HABIT') coreClasses.push('habiting');

  const glowStyle = {
    filter: `brightness(${0.5 + glowIntensity * 0.5})`,
    boxShadow: `0 0 ${20 + glowIntensity * 30}px ${color}`,
  };

  return (
    <div className="living-orb-shell" onClick={handleClick} title={`Mode: ${cognitiveMode} - Click to ask CALI`}>
      <div className={coreClasses.join(' ')} style={{ color, ...glowStyle }}>
        <div className="living-orb-glow" style={{ background: color }} />
        <div className="living-orb-rings">
          <span />
          <span />
          <span />
        </div>
        <div className="living-orb-surface" />
      </div>
      <div className="living-orb-status">
        <strong>{cognitiveMode}</strong>
        <span>{statusLine}</span>
      </div>
      <div className="permission-toggles" onClick={(e) => e.stopPropagation()}>
        {[
          ['desktop', 'Desktop'],
          ['browser', 'Browser'],
          ['voice', 'Voice'],
          ['listening', 'Listening'],
        ].map(([key, label]) => (
          <div
            key={key}
            className={`permission-toggle ${permissions[key] ? 'on' : 'off'}`}
            onClick={() => togglePermission(key)}
            title={`${label} permission: ${permissions[key] ? 'on' : 'off'}`}
          >
            <span className="dot" />
            <span>{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

export default LivingOrb;
