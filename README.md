# CALI Floating Assistant Orb (Orb_Assistant)

A screen-aware, cursor-tracking AI assistant that integrates with UCM_4_Core ECM for cognitive enhancement.

This root README is the **authoritative** Orb documentation for this workspace. Module READMEs remain intact as historical or component-specific references.

## Architecture Note

Earlier versions of this repo included an "Immutable System Law" describing a binding Core-4 cognitive architecture.

That text is no longer authoritative for this workspace. The current Orb runtime does not implement that model end to end, and the remaining Core-4-related material in the repo is historical, partial, or stubbed.

See [IMMUTABLE_LAW.md](IMMUTABLE_LAW.md) for the deprecation note.

## Swarm Audit Doctrine

Advanced swarm audit policy is defined in [ORB_SWARM_AUDIT_DOCTRINE.md](ORB_SWARM_AUDIT_DOCTRINE.md).

This doctrine is specific to Dock Station and swarm governance flows where Prime ORB mission manifests, prime-ID participation products, trace hashes, nonces, and timestamp/TTL verification are required for forensic auditability.

### STRICT_COHERENCE (Canonical Lock)

The Prime ORB swarm-count policy is locked under strict coherence:

- Canonical allowed swarm counts: `2, 3, 5, 7, 11`
- Any requested/manual/query-derived count must be normalized to the approved canonical set only
- No runtime path may expand swarm counts beyond the canonical set
- Audit lineage and return signatures must reference this canonical set

## Features

- ðŸ–¥ï¸ **Screen Awareness**: Sees your screen and understands UI elements
- ðŸ–±ï¸ **Cursor Tracking**: Maintains ~350px distance from cursor
- ðŸ§  **Cognitive Integration**: Uses ECM and SKG for intelligent assistance
- ðŸ¤– **Automation**: Can automate typing and clicks with permission
- ðŸ“Š **Habit Learning**: Learns your usage patterns via SKG
- ðŸ”’ **Privacy-First**: Requires explicit permission for all features

## Architecture

### Core Components

1. **FloatingAssistantOrb** (Python)
   - Screen capture and OCR
   - Cursor tracking and positioning
   - ECM integration for cognitive processing
   - SKG habit learning
   - **Recently cleaned**: Organized imports, centralized path setup, improved error handling

2. **OrbController** (Python)
   - Cognitive processing controller with epistemic gravity field integration
   - **Recently cleaned**: Restructured imports, cleaner EGF setup, better error boundaries

3. **CALI SKG** (Python)
   - Machine learning subsystem with optional component loading
   - **Recently cleaned**: Consolidated optional imports into structured configuration

4. **Electron Main Process**
   - IPC bridge between Python and renderer
   - Window management
   - Permission handling

5. **Renderer UI**
   - Floating orb UI (vanilla `simple-orb.js` in current Electron runtime)
   - Optional React orb (`FloatingOrb.jsx`) for UCM-driven motion and HUD

### Recent Code Organization (2026-04-14)

The codebase has been comprehensively cleaned and organized while preserving all functionality:

- **Import Organization**: Separated standard library, third-party, and local imports
- **Path Resolution**: Centralized component path discovery for SF-ORB and ACP 3.0
- **Configuration Management**: Structured optional dependency loading with graceful degradation
- **Error Handling**: Improved error boundaries with informative logging
- **Dependencies**: Grouped requirements.txt by category (scientific, ML, web, audio, system, GUI)

All changes maintain backward compatibility and component interconnections.

### Data Flow

- Screen â†’ OCR/Vision â†’ ECM â†’ Task Planning â†’ Automation
- Cursor â†’ Position Tracking â†’ Orb Movement
- User Habits â†’ SKG Learning â†’ Personalized Assistance

## Runtime Topology

- **Electron main â†” Python**: JSON messages over stdio via `python-shell`.
- **Renderer â†” Electron main**: IPC (`orb:cursor-move`, `orb:get-status`, `orb:cognitive-pulse`).
- **Renderer â†” UCM**: WebSocket + optional HTTP performance polling (React orb path).
- **Optional WS stub**: Local dev stub for status/query echo.
- **Swarm substrate (local)**: SQLite store at `system/swarm/substrate.db` for shared research cache, mesh tasks, and promoted knowledge.

## Swarm Mission Routing (Prime ORB)

The renderer swarm is mission-gated and deterministic.

- Mission flow grammar: `out_spin -> out_dart -> in_arc -> in_loop -> ingest`
- Deployment modes: `research` and `diagnostics` only
- Normal chat/greetings/basic answers: no swarm deployment
- Return swarm is gated by pending missions (no outbound mission -> no inbound return visual)

Classifier priority:

1. diagnostics if failure/repair language is present
2. research if research language is present
3. no swarm otherwise

Precedence example:

- `research why Ollama is failing` routes to diagnostics (amber), not research (blue)

Prime-number shard counts are constrained to the approved set:

- `2, 3, 5, 7, 11`

Color semantics:

- research outbound: blue
- diagnostics outbound: red
- inbound success: green
- inbound warning: amber
- inbound fault: red

## Epistemic Gravity Field Wiring

- **Runtime module path**: `R:\Orb_Assistant_Desktop\modules\Epistemic_Gravity_Field\space_field.py`
- **Loader location**: `electron/src/orb_controller.py`
- **Enable switch**: `ORB_ENABLE_EGF_TENSOR=1`
- **Deterministic path override**: `ORB_EGF_ROOT=R:\Orb_Assistant_Desktop\modules\Epistemic_Gravity_Field`

Path resolution is now env-first (`ORB_EGF_ROOT`) with workspace default fallback to `modules/Epistemic_Gravity_Field`.

## Ports & Endpoints

> **This section reflects the currently active runtime configuration (non-Docker).**

### UCM WebSocket (React orb path)
- **WebSocket**: `ws://localhost:8000/ws/orb_assistant`
  - Used by `electron/src/components/FloatingOrb.jsx`
  - Handshake: `ORB_HANDSHAKE` with `orb_id` and `capabilities`
  - Receives `lerp_optimization` and `drift_preference` updates

### UCM HTTP (React orb path)
- **HTTP**: `http://localhost:8000/api/orb/performance`
  - Polled every 5s by `FloatingOrb.jsx` for performance HUD
  - Note: the mock server in `electron/src/ucm_server.py` does **not** implement this endpoint yet

### Mock UCM WebSocket Server
- **Server**: `electron/src/ucm_server.py`
  - Binds on `0.0.0.0:8000`
  - WebSocket path: `/ws/orb_assistant`

### WS Stub (local dev)
- **WebSocket**: `ws://localhost:${ORB_WS_PORT}` (default `9876`)
  - Run with `npm run ws:stub` from `electron/`
  - Echoes status/query responses for UI testing

## Configuration & Environment Variables

- `ORB_DISABLE_PYTHON_BRIDGE=1`
  - Disables Python bridge startup in Electron main.
- `ORB_PYTHON_PATH`
  - Absolute Python executable used by Orb bridge (set to your CUDA-enabled runtime for GPU paths).
- `ORB_WS_PORT`
  - Port for the local WS stub (`electron/ws-stub.js`).
- `ORB_PRIMARY_DISPLAY_ONLY=1`
  - Runs Orb window only on the primary display (lowers renderer load on multi-monitor setups).
- `ORB_CURSOR_SAMPLE_MS`
  - Cursor sampling interval in milliseconds (`16` default, `33` recommended for balanced mode).
- `ORB_CURSOR_CLEARANCE_EXTRA_PX`
  - Adds extra cursor distance padding to keep the orb farther from the pointer.
- `ORB_TOPMOST_WATCHDOG_MS` / `ORB_TOPMOST_REFRESH_MS`
  - Topmost enforcement cadence; increase values to reduce maintenance overhead.
- `ORB_ENABLE_DESKTOP_PRESENCE=0`
  - Disables desktop presence memory background runtime.
- `ORB_ENABLE_SWARM_EXTENSION=1`
  - Enables local swarm runtime bridge and shared substrate persistence.
- `ORB_SWARM_HUD=1`
  - Dev-only swarm mini-HUD overlay in the renderer (default off).
  - HUD shows mission mode, active phase, outbound/inbound counts, pending missions, last result, timing window snapshot, and EGF snapshot.
- `ACP3_ROOT`
  - Absolute path to the single ACP 3.0 runtime (`R:\cochlear_processor_3.0` on Windows, `/mnt/r/cochlear_processor_3.0` under WSL).
- `ACP3_SKG_PATH`
  - R-drive hearing SKG used by ACP 3.0 (`system/CALI_System/memory/hearing_skg_v3.json`).
- `ACP3_AUDIO_CACHE`
  - R-drive output cache for ACP 3.0 voice artifacts.
- `CUDA_VISIBLE_DEVICES`, `CALI_OLLAMA_DEVICE`, `CALI_OLLAMA_NUM_GPU`
  - GPU offload settings used by the desktop launcher to keep the local Qwen 2.5 3B model on CUDA.
- `ACP_WHISPER_DEVICE=auto`
  - Optional local Whisper device selection when the active Python runtime has Whisper installed.
- Python bridge sets `PYTHONIOENCODING=utf-8` internally for clean JSON I/O.

## Setup & Run (Windows)

### Prerequisites
- Node.js 16+
- Python 3.8+
- Tesseract OCR

### Install Dependencies

- Python deps (from `electron/`):
  - `pip install -r requirements.txt`
- Node deps (from `electron/`):
  - `npm install`
- Tesseract OCR:
  - Download from GitHub releases (Windows installer)

### Run the Orb

From `electron/`:
- `npm start`

Historical note: earlier docs referenced `npm run build`, but the current `package.json` exposes `pack` and `dist` instead. Use those if you need a packaged build.

## Session Records & Development History

Development sessions are documented in `electron/SESSION_RECORD_*.md` files:

- **SESSION_RECORD_2026-04-14_120000_CDT.md**: Codebase review, testing framework development, comprehensive cleanup and organization
- Previous sessions archived for historical reference

## Development Notes

### Project Structure (Electron)

```
electron/
â”œâ”€â”€ main/
â”‚   â”œâ”€â”€ main.js          # Electron main process
â”‚   â”œâ”€â”€ preload.js       # Secure IPC bridge
â”‚   â””â”€â”€ orb-bridge.js    # Python integration
â”œâ”€â”€ src/
â”‚   â”œâ”€â”€ components/
â”‚   â”‚   â”œâ”€â”€ FloatingOrb.jsx
â”‚   â”‚   â””â”€â”€ FloatingOrb.css
â”‚   â”œâ”€â”€ main.jsx         # React entry point (not used by default index.html)
â”‚   â”œâ”€â”€ simple-orb.js    # Default Electron renderer orb
â”‚   â””â”€â”€ index.html       # App HTML
â”œâ”€â”€ requirements.txt     # Python dependencies
â”œâ”€â”€ package.json         # Node.js config
â””â”€â”€ launch.sh            # Launch script (Unix)
```

### Adding New Features

1. Add Python methods to `FloatingAssistantOrb` (see `electron/src/floating_assistant_orb.py`).
2. Expose via IPC in `electron/main/orb-bridge.js`.
3. Use in renderer via `window.electronAPI` (see `electron/main/preload.js`).

## Security & Privacy

- All screen data is processed locally.
- No data is sent to external servers by default.
- User must explicitly grant permissions.
- Automation requires additional permission.
- All data is encrypted in the UCM vault system.

## Troubleshooting

### Orb Not Appearing
- Check console for permission errors.
- Ensure screen access permission is granted.
- Verify Python dependencies are installed.

### Orb Pulses but Doesnâ€™t Move
- The default Electron UI (`simple-orb.js`) only moves on mouse proximity.
- Ensure the window is receiving mouse events and your cursor is within ~350px.
- For UCM-driven drift and richer motion, switch to the React orb (`FloatingOrb.jsx`).

### Performance Issues
- Reduce screen capture region size.
- Adjust cursor tracking frequency.
- Disable vision model if not needed.

### Permission Errors
- Restart the application.
- Check OS security settings.
- Reinstall with proper permissions.

## Quick Resume (2026-05-24)

- Last known startup command:
  - `cd R:\R_Drive_Substrate\Orb_Assistant_Desktop\electron\.orb-assistant`
  - `npm run dev`
- Current critical issue:
  - Electron is up, but ORB child process can exit with `code=1`, causing repeated `orb:set-state` / `orb:set-listening` handler failures.
- Patch applied:
  - `electron/main/orb-bridge.js` now prefers `R:\R_Drive_Substrate\Services\qwen_tts_312\Scripts\python.exe` before generic local Python installs.
  - Bridge exit errors now include a Python `stderr_tail` snippet for direct root-cause diagnosis.
- UI tuning applied:
  - `electron/src/ui/orb-dock-station.jsx` and `electron/src/ui/orb-dock-station.bundle.js` pulse is slower and less transparent.
- Next recovery step:
  - Re-run dev command and, if failure persists, fix the exact Python module/import named inside `stderr_tail`.

## Quick Resume (2026-05-24, Motion Refactor)

- Movement architecture now routes through:
  - `electron/src/interface/companion_intent.js`
  - `electron/src/hlsf_geometry/field_motion.js`
  - `electron/src/orb-renderer.js` animation loop (consumes intent + field motion only)
- Cursor is now an input signal, not the direct movement authority.
- Playful movement is disabled by default (`ORB_PLAYFUL_IDLE_ENABLED` must be `1` to enable).
- Validation completed:
  - `node --check src/interface/companion_intent.js`
  - `node --check src/hlsf_geometry/field_motion.js`
  - `node --check src/orb-renderer.js`

## Dock Runtime Truth Layer (2026-05-25)

Dock Station is treated as the operator cockpit and black-box recorder. The backend now emits a single runtime_snapshot consumed by the Dock runtime panel, and Dock Talk transactions append to CALI_System/runtime_logs/dock_transactions.jsonl.

The panel distinguishes Dock channel connectivity from listening state. CHANNEL CONNECTED / LISTENING OFF is valid and no longer appears as disconnected. Voice state is explicit: QWEN ACTIVE, KOKORO FALLBACK, VOICE DEGRADED, or NO VOICE.

UCM remains opt-in through ORB_ENABLE_UCM_STATUS_CHECK=1; Kokoro fallback remains available behind Qwen.

