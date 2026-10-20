
# CALI Orb Four-Layer State Machine — Architecture Summary

## What Was Built

Four new modules that replace the flat mutable `orb_state` dict with a
proper four-layer state authority, plus integration guides.

---

## The Four Layers

| Layer | Authority | Writes From | Reads By |
|-------|-----------|-------------|----------|
| **desired** | User / Bridge | DockStation, UI clicks, bridge commands | Effective derivation |
| **runtime** | Subsystems | Health probes (mic, TTS, LLM, presence) | Effective derivation |
| **effective** | CALI (derived) | Auto-derived from desired ∩ runtime ∩ policy | get_status(), behaviors, bridge |
| **activity** | Execution | Behavior methods, command handlers | Bridge status, debug |

---

## Files Created

### Core Module
- **`orb_state_machine.py`** — CALIStateMachine class. The truth authority.
  - Four layers: desired, runtime, effective, activity
  - Every state report: `value + source + timestamp + error`
  - Command lifecycle: ACCEPTED → EXECUTING → COMPLETED/FAILED/TIMEOUT
  - Motion: named target + completion event (not just enabled flag)
  - Checkout validation: files only relevant if in active checkout
  - Pure read `get_status()` — never probes, never mutates

### Functional Modules
- **`orb_lifecycle.py`** — OrbLifecycle class
  - Wraps start/stop/get_status
  - Background health probe thread writes to RUNTIME layer
  - `get_status()` is pure read from EFFECTIVE layer
  - `refresh_runtime_health()` one-shot for startup

- **`orb_command_router.py`** — OrbCommandRouter class
  - Replaces inline stdin/stdout loop
  - Every command gets request_id + full lifecycle
  - Timeout handling with diagnostic capture
  - Handlers: set_listening, listen_once, get_status, set_voice, set_motion,
    set_cognition, orb_query, orb_speak, shutdown, diagnose

- **`orb_behavior_runtime.py`** — OrbBehaviorRuntime class
  - Delegates: cursor movement, cognitive emergence, idle cognition,
    whistle detection, summon detection, verbal commands
  - Every behavior checks effective state before executing
  - Records activity state + completion result

### Integration Files
- **`floating_assistant_orb_main_INTEGRATION.py`** — Shows exact _attach_modules() changes
- **`orb-bridge_UPDATED.js`** — Shows bridge status emission with new format

---

## The Listening Problem — Solved

### Before (broken):
```
DockStation: "Enable listening" → bridge → Python
Python: set speech_enabled = true
Python: get_status() → probes mic → mic not ready → returns false
DockStation: Toggle stays off (but WHY? No info)
User: Plugs in mic
Python: get_status() → probes mic → mic ready → returns true
DockStation: Toggle turns on
```
**Problem:** get_status() was a mutator. No visibility into why it failed.

### After (fixed):
```
DockStation: "Enable listening" → bridge → Python
Python: desired.listening.enabled = true (ACCEPTED)
Python: effective.can_listen = false (derived)
Python: block_reason = "mic_unavailable"
Python: block_source = "MicCapture"
Python: block_checked_at = 1712345678.901
Bridge: emits listening_mode with full provenance
DockStation: Toggle stays OFF, tooltip: "Microphone unavailable"

User: Plugs in mic
Health probe: runtime.mic_available = true
Python: effective.can_listen = true (auto-derived)
Bridge: emits update
DockStation: Toggle turns ON
```

---

## The Motion Problem — Solved

### Before (broken):
```
DockStation: "Enable motion" → Python
Python: motion_enabled = true
ORB: Never moves (no target, no destination)
DockStation: Toggle stays on forever
```

### After (fixed):
```
DockStation: "Move to cursor" → Python
Python: desired.motion.enabled = true
Python: motion.target = "cursor"
Python: motion.started_at = 1712345678.901
ORB: Begins moving toward cursor
Python: motion.completed_at = 1712345679.234
Python: motion.result = "success"
Bridge: emits motion_status with full completion
DockStation: Shows "Following cursor" → "Arrived at cursor"
```

---

## Command Lifecycle Example

```
Bridge sends: {"type":"set_listening","enabled":true,"request_id":"abc123"}

Router: start_command("abc123", "set_listening", {...})
  → phase: ACCEPTED
  → emit: {"type":"command_accepted","request_id":"abc123"}

Router: transition_command("abc123", EXECUTING)
  → call _handle_set_listening()
  → desired.listening.enabled = true
  → derive effective → can_listen = false (mic unavailable)
  → return {"listening_enabled":true, "can_listen":false, ...}

Router: transition_command("abc123", COMPLETED, result={...})
  → emit: {"type":"command_completed","request_id":"abc123","result":{...}}

State machine now has:
  commands["abc123"] = {
    request_id: "abc123",
    command_type: "set_listening",
    phase: "COMPLETED",
    accepted_at: 1712345678.901,
    executing_at: 1712345678.905,
    completed_at: 1712345678.912,
    duration_ms: 11.0,
    result: {...}
  }
```

---

## Diagnostic Example

```python
# In Python (or via diagnose command)
sm.diagnose_listening()
# Returns:
# {
#   "desired": {"enabled": {"value": true, "source": "bridge", ...}},
#   "runtime": {"mic_available": {"value": false, "source": "MicCapture", 
#              "error": "timeout waiting for CP3 listener ready", ...}},
#   "effective": {"can_listen": false, "block_reason": "mic_unavailable",
#                 "block_source": "MicCapture", ...},
#   "activity": {"state": "listening_inactive", ...},
#   "diagnosis": "listening: BLOCKED — timeout waiting for CP3 listener ready
#                 (reported by MicCapture)"
# }
```

---

## Checkout Validation

```python
sm = CALIStateMachine(checkout_path=Path("R:\Orb_Assistant_Desktop"))

# File in correct checkout
sm.validate_checkout(Path("R:\Orb_Assistant_Desktop\src\orb.py"))
# → True

# File in wrong checkout (legacy path)
sm.validate_checkout(Path("R:\R_Drive_Substrate\Orb_Assistant_Desktop\src\orb.py"))
# → False
```

---

## Integration Steps

### 1. Copy the four .py files into your Python project
```
orb_state_machine.py
orb_lifecycle.py
orb_command_router.py
orb_behavior_runtime.py
```

### 2. Update floating_assistant_orb_main.py
Replace `_attach_modules()` with the version in `floating_assistant_orb_main_INTEGRATION.py`.
The `_main()` function body stays exactly the same.

### 3. Update orb-bridge.js
Replace status handling with the version in `orb-bridge_UPDATED.js`.

### 4. Update FloatingOrb.jsx (renderer)
- Listen for `block_reason` in listening_mode
- Show tooltip when toggle is blocked
- Listen for motion target + completion
- Show command lifecycle in debug panel

---

## Behavioral Test Plan (Acceptance Criteria)

| Step | Action | Expected State Change |
|------|--------|----------------------|
| 1 | User presses "Enable Listening" | desired.listening.enabled = true |
| 2 | Bridge sends set_listening | Command lifecycle: ACCEPTED |
| 3 | CALI checks mic runtime | runtime.mic_available = false |
| 4 | CALI derives effective | effective.can_listen = false, block_reason = "mic_unavailable" |
| 5 | Bridge emits listening_mode | enabled: false, reason: "mic_unavailable" |
| 6 | DockStation shows truth | Toggle stays off, tooltip: "Microphone unavailable" |
| 7 | User plugs in mic, runtime reports | runtime.mic_available = true |
| 8 | CALI re-derives | effective.can_listen = true |
| 9 | Bridge emits update | enabled: true |
| 10 | DockStation updates | Toggle turns on |

---

## Key Architectural Principles

1. **CALI owns the truth** — No competing authorities
2. **get_status() is pure read** — Never probes, never mutates
3. **Health probes write to RUNTIME** — Only OrbLifecycle probes subsystems
4. **Effective state is derived** — Intersection of desired + runtime + policy
5. **Every command has lifecycle** — ACCEPTED → EXECUTING → COMPLETED/FAILED/TIMEOUT
6. **Motion has named target + completion** — Not just enabled flag
7. **Checkout validation** — Files only relevant in active checkout
8. **Source + timestamp on every report** — Never stale booleans
