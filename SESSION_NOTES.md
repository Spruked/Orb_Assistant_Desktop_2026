# ORB Build Session Notes

> IMPORTANT NOTE (2026-05-24): Ignore any references to `/mnt/agents/upload/...` paths.
> Those files belong to Kimi Moonshot sandbox workflows and are not part of this ORB runtime or repository context.
> Do not use or request them in this workspace.
> Running changelog of build decisions, changes, and session handoffs.
> Updated each session. Newest entries at the top.

---

## Session: 2026-05-31 | GPT-5 Codex | Mesh Guardrail Audit + Cross-Authority Verification

### Changes This Session
- Audited live CRM + Prime Mail + ORB runtime alignment against substrate authority contract.
- Verified ORB mesh/manifest guardrail readiness fields are present and valid:
  - `manifest_validation_status`
  - `write_tools_enabled`
  - `write_tools_allowed_by_permissions`
  - `write_tools_requiring_user_approval`
- Verified blocked-write guardrail behavior (`permission_flag_disabled` for draft-prepare when `ORB_ALLOW_EMAIL_DRAFTS=0`).
- Verified allowed-read behavior (`orb.mail.inbox.summary` returned `200` and live inbox payload).
- Verified no ORB-side duplicate contact/message store introduced by current mesh/manifest implementation.

### Runtime Verification Summary
- CRM health: `http://127.0.0.1:21000/health` -> `ok`
- Prime Mail health: `http://127.0.0.1:19000/api/health` -> `ok`
- ORB readiness: TestClient checks for `/api/v1/readiness` -> `ok`
- Cross-app contact parity confirmed for:
  - `substrate.sync.test+1780199795@example.com`
  - Same contact visible in both CRM and Prime Mail.

### Known Issue
- Inbox summary payload-noise issue was mitigated in this session by compacting ORB summary/search outputs to metadata + cleaned preview text; full payload remains available via `orb.mail.message.get`.

## Session: 2026-04-30 | Claude Sonnet 4.6 | CALI-UCM OOM fix + Testing Ladder

### Changes

#### `R:\CALI-UCM\SuccessorRepresentation.ts`
- Replaced `computeEigendecomposition()` — eliminated 8.59GB Float64Array allocation (`32768^2 × 8 bytes`)
- Empty SR: immediate zero-vector fallback, no matrix allocated
- Non-empty SR: caps to 256 visited states, max 256×256 matrix (~512KB), scatter-back to full dim^3 vectors
- Confirmed fix: adapter now returns `{ routed: true }` instead of `CALI_UCM_TIMEOUT`

#### `R:\CALI-UCM\` — Testing Ladder (new files)
- `package.json`, `vitest.config.ts` — Vitest 2.x + v8 coverage (90/90/95/90 thresholds)
- `tests/helpers/` — GovernanceDenialError, governed-step, seeded-random, report-writer
- `tests/level1/smoke.test.ts` — 10 tests S-01..S-10 → WIRING_PROVEN
- `tests/level2/cognitive-ethical.gate.test.ts` — 18 tests G-01..G-18 → GOVERNANCE_PROVEN
- `tests/integration/cognitive-ethical.integration.test.ts` — 10 tests I-01..I-10 @ 100 iters
- `tests/e2e/e2e.trials.test.ts` — 10 tests E-01..E-10 @ 100/500 iters

#### `R:\CALI-UCM\IntegratedCore4Runtime.ts` — DIAGNOSTIC INSTRUMENTATION (PENDING REMOVAL)
- Added `fs.appendFileSync` stepDiag() calls at every stage — used to pinpoint OOM location
- **Must be removed next session** after test results are confirmed

### Test Run Status
- `npx vitest run --coverage` launched as background task at session end — results pending
- All DIAG logs show stepWithTransport completing end-to-end (25–700ms per step)
- Reports will appear in `R:\orb_mesh\exports\desktop\test_reports\` when complete

### Pending Next Session
1. Retrieve vitest pass/fail results + coverage metrics
2. Remove DIAG instrumentation from IntegratedCore4Runtime.ts
3. Act on promotion recommendation (PROMOTE / CONTINUE_TRIAL / HALT)
4. Session preservation: `R:\orb_mesh\exports\desktop\test_reports\session_2026-04-30\`

---

## Session: 2026-04-29 | codex | Platinum ORB desktop defaults + CP3/Kokoro validation

### Changes

#### `orb-instance.windows.ps1`
- Set default product identity to `Platinum ORB Desktop Assistant`.

#### `orb-instance.local.ps1`
- Set Tier 3 Dock startup defaults.
- Keeps CP3/Whisper/Kokoro configured but disables audio preload and continuous listening until a Windows-to-WSL mic backend is confirmed.
- Leaves swarm auto-start off so the bridge reaches ready state and mesh heartbeat deterministically.
- Leaves desktop presence auto-start off because the WSL launch path can block during presence initialization.
- Set local Qwen route defaults:
  - `ORB_LLM_ROUTE=local`
  - `ORB_LOCAL_LLM_ENDPOINT=http://127.0.0.1:11434`
  - `ORB_LOCAL_LLM_MODEL=qwen2-1_5b-instruct-q4_0.gguf`
- Added Kokoro espeak lib/data path wiring for WSL.

#### `cochlear_processor_3.0/orb_acp3_adapter.py`
- Added Kokoro/phonemizer compatibility shim for `EspeakWrapper.set_data_path`.
- Added explicit Kokoro `EspeakConfig` wiring from env.

#### `electron/src/cali_skg.py`
- Defaulted CALI state to governed local Qwen route with retained Orb voice.

#### `electron/src/ui/orb-dock-station.jsx`
- Defaulted Dock Station LLM controls to local Qwen endpoint/model.

#### `ORBS_MULTI_DOCK_PLAN.md`
- Added eight-slot primary/subordinate Dock Station plan for ORBS.

#### Phase 1 substrate audit fixes
- Added deterministic `r_drive_path()` resolver in `electron/src/cali_skg.py`.
- Replaced direct `R:\...` research/cache/substrate constants with resolver-backed paths.
- Updated `instance.manifest.json` product identity and split launcher metadata into `launchers.windows` and `launchers.wsl`.
- Quarantined malformed duplicate path:
  - from `R:\Orb_Assistant_Desktop\electron\ROrb_Assistant_Desktopsystem`
  - to `R:\_quarantine\malformed_paths\Orb_Assistant_Desktop_electron_bad_system_path_2026-04-29`

### Verification
- JS syntax checks passed.
- WSL Python compile checks passed.
- CP3 adapter imports online.
- Whisper import available.
- Kokoro ONNX initialized with configured model, voices, and espeak data.
- Kokoro generated a WAV in `R:\Orb_Assistant_Desktop\system\CALI_System\voice_cache`.
- WSL `sounddevice` currently reports no input device; continuous Alexa-style listening needs a Windows mic bridge or Pulse source before being made default.
- Audio preload was left off because WSL microphone discovery can block the bridge before mesh heartbeat.
- Desktop heartbeat proven live at `R:\orb_mesh\exports\desktop\state_snapshots\heartbeat.json`.

---

## Session: 2026-04-24 | codex | Windows/R drive scan + ORb launch

### Handoff Signature
```
Substrate:  R:\Orb_Assistant_Desktop
Mesh:       R:\orb_mesh
Branch:     main | e76246bac
Launcher:   R:\Orb_Assistant_Desktop\launch_desktop_orb.ps1
```

### R Drive Scan
- Top-level scan found 31 active directories and 12 files under `R:\`, excluding `$RECYCLE.BIN` and `System Volume Information`.
- Primary ORb runtime copy remains `R:\Orb_Assistant_Desktop`.
- Shared ORb mesh remains `R:\orb_mesh` with `audit`, `checkpoints`, `exports`, `heartbeats`, `imports`, `locks`, `manifests`, `promoted_knowledge`, `results`, `tasks`, and `tpc_handoffs`.
- Mesh manifest `R:\orb_mesh\manifests\orb_mesh_manifest.json` declares instances: `wsl`, `desktop`, `web`; protocol: `append_only_with_checkpoint`; audit enabled.
- Desktop launcher loads `orb-instance.windows.ps1` and local override `orb-instance.local.ps1`, then starts Electron from `electron\node_modules\electron\dist\electron.exe`.
- Local override routes the Python bridge through WSL at `/home/bryan/pro_prime_env/bin/python`, with mesh root `/mnt/r/orb_mesh` and system root `/mnt/r/Orb_Assistant_Desktop/system`.

### Launch Action
- ORb started after notes update using `launch_desktop_orb.ps1`.
- Launcher process started successfully; Electron child processes came up from `R:\Orb_Assistant_Desktop\electron\node_modules\electron\dist\electron.exe`.
- Electron spawned the WSL Python bridge through `/home/bryan/pro_prime_env/bin/python`.
- Follow-up process check after one heartbeat interval still showed the Electron process group active.

### Pending / Next
- [ ] Confirm fresh desktop heartbeat after ORb is running; no `heartbeat.json` was observed under `R:\orb_mesh` during immediate or one-interval post-start checks.
- [ ] If startup fails, check `R:\Orb_Assistant_Desktop\.orb-launch.log`, `R:\orb_stderr.txt`, and Electron bridge output.

---

## Session: 2026-04-24 | codex | ORb multi-monitor cursor-follow fix

### Changes

#### `orb-instance.local.ps1`
- Set `ORB_SINGLE_ORB_MULTI_DISPLAY=0` so Windows uses one transparent overlay per monitor instead of one virtual overlay stretched across all monitors.
- Enabled cursor-follow mode with:
  - `ORB_CURSOR_FOLLOW=1`
  - `ORB_CURSOR_FOLLOW_OFFSET_X=120`
  - `ORB_CURSOR_FOLLOW_OFFSET_Y=-90`
  - `ORB_CURSOR_FOLLOW_LERP=0.24`

#### `electron/src/orb-renderer.js`
- Added cursor-follow env controls.
- Added `getCursorFollowTarget()` and made the animation loop follow the current cursor with a configurable offset when `ORB_CURSOR_FOLLOW` is enabled.
- Retained autonomous drift path as fallback when cursor-follow is disabled.
- Removed the inactive-display opacity gate so the orb remains visible even if monitor routing reports the active display incorrectly.

### Verification
- `node --check electron/src/orb-renderer.js` passed.
- Restarted ORb after patch.
- New Electron main process observed: `25136`.
- Follow-up relaunch after visibility gate removal produced main Electron process `20360` with WSL bridge children active.

---

## Session: 2026-04-24 | codex | Dock/Orb render recovery

### Changes

#### `orb-instance.local.ps1`
- Temporarily set `ORB_PRIMARY_DISPLAY_ONLY=1` to stabilize rendering on the detected Windows display set.
- Kept Dock startup enabled with `ORB_OPEN_DOCK_ON_START=1`.

#### `electron/main/main.js`
- Added `orb-render-diagnostics.log` renderer diagnostics for Dock, Studio, and Orb shell windows.
- Forced Dock Station to open on ORb startup.
- Changed Dock Station to `show: true` and added forced `show()/focus()` after creation, page load, and timeout.
- Added forced show paths for the Orb shell after page load/timeout.
- Lowered orb topmost behavior while Dock Station is visible so the full-screen transparent Orb overlay does not mask the Dock window.

### Verification
- `node --check electron/main/main.js` passed.
- Relaunched ORb.
- Dock Station is now the visible main Electron window: PID `23252`, title `Orb Dock Station`, responding `True`.
- Diagnostics show Dock bundle console output, confirming the Dock renderer executed.
- Orb shell still loads successfully with `did-finish-load` in diagnostics.

---

## Session: 2026-04-24 | codex | CP 3.0 WSL runtime clarification

### Findings
- The live Electron bridge already launches Python through WSL when `ORB_PYTHON_PATH` is `/home/bryan/pro_prime_env/bin/python`.
- Direct WSL import verified:
  - `/mnt/r/cochlear_processor_3.0/orb_acp3_adapter.py`
  - `/mnt/r/cochlear_processor_3.0/cochlear_processor_v3.py`
- `electron/main/skg-worker.js` is not the CP 3.0 path. It is a JS governance/vault/LLM worker and does not touch audio, hearing, or Cochlear Processor 3.0.
- CP 3.0 is wired through `electron/src/floating_assistant_orb.py` and `R:\cochlear_processor_3.0\orb_acp3_adapter.py`.
- CP 3.0 was lazy-loaded only on voice/listen/text-frame demand unless `ORB_PRELOAD_AUDIO_RUNTIME=1` was set.

### Changes
- Added `CP3_ROOT=/mnt/r/cochlear_processor_3.0` while preserving legacy `ACP3_ROOT` compatibility.
- Set `ORB_PRELOAD_AUDIO_RUNTIME=1` so the CP 3.0 adapter initializes at startup.
- Set `ORB_ENABLE_ACP_TEXT_FRAME=1` explicitly for CP-backed text input framing.
- Updated `floating_assistant_orb.py` to prefer `CP3_ROOT`, then fall back to `ACP3_ROOT`.

### Verification
- `node --check electron/main/main.js` passed.
- `node --check electron/main/orb-bridge.js` passed.
- WSL `py_compile` passed for:
  - `/mnt/r/Orb_Assistant_Desktop/electron/src/floating_assistant_orb.py`
  - `/mnt/r/cochlear_processor_3.0/orb_acp3_adapter.py`
- Relaunched ORb; Dock Station running as PID `23980`, WSL bridge active.

---

## Session: 2026-04-24 | codex | Single Orb virtual desktop overlay

### Desired State
- One transparent overlay spanning the virtual desktop.
- One visible Orb body inside that overlay.
- Orb visual remains fixed-size.
- Cursor-follow uses global desktop coordinates mapped into overlay-local coordinates.
- No per-monitor Orb bodies and no duplicate Orb visuals.

### Changes

#### `orb-instance.local.ps1`
- Restored virtual desktop mode:
  - `ORB_PRIMARY_DISPLAY_ONLY=0`
  - `ORB_SINGLE_ORB_MULTI_DISPLAY=1`
  - `ORB_CURSOR_FOLLOW=1`
  - `ORB_CURSOR_SAMPLE_MS=33`

#### `electron/main/main.js`
- Kept the single virtual display descriptor path.
- Added explicit cursor payload metadata:
  - `globalX/globalY`
  - `overlayX/overlayY`
  - `overlayWidth/overlayHeight`
  - `virtualDesktop`
- Cursor `x/y` remains overlay-local: `global cursor - virtual overlay origin`.

#### `electron/src/orb-renderer.js`
- Reinforced fixed-size Orb visual with min/max width/height, aspect ratio, and no flex growth.
- Orb position remains controlled by `left/top` plus translate transform inside the overlay.

#### `electron/src/orb-shell.html`
- Added defensive root/body rules to prevent zoom/transform scaling of the Orb visual.

### Verification
- `node --check electron\main\main.js` passed.
- `node --check electron\src\orb-renderer.js` passed.
- Relaunched ORb.
- Dock Station running as PID `14212`.
- Diagnostics confirm the Orb shell is using the virtual overlay id: `orb:__orb_virtual_display__`.

---

## Session: 2026-04-18 | claude-sonnet-4-6 | VSCode/Windows  *(continued — orb drift + voice hotkey)*

### Changes

#### `electron/src/orb-renderer.js` — Orb no longer drifts to screen center
- Added `ORB_HOME_X_RATIO = 0.82`, `ORB_HOME_Y_RATIO = 0.80` constants and `getHomePosition()` helper
- `chooseAutonomousDriftTarget` (no-cursor branch): replaced `viewportCenter` with `homePos` (bottom-right zone); candidate scoring now penalises distance from home, not center
- `buildSteeringVector` edge-slack recovery: now pulls toward home position instead of center
- Stuck-at-edge recovery: targets home + jitter instead of center + jitter
- `ensureCursorClearance` last-resort fallback: `getHomePosition()` instead of `0.5, 0.5`

#### `electron/main/main.js` — Global hotkey for voice without clicking dock
- Added `globalShortcut` to Electron imports
- Registered `Ctrl+Shift+Space` (Win/Linux) / `Cmd+Shift+Space` (Mac) in `whenReady` → calls `listenOnce()`
- Unregisters all shortcuts on `before-quit`
- Note: **double-click the orb** also triggers voice capture (already wired)

---

## Session: 2026-04-18 | claude-sonnet-4-6 | VSCode/Windows  *(continued)*

### Changes — HLSF Visualization + Orb Registry Panel

#### Continuation — live snapshot wiring completed

#### `electron/src/ui/orb-dock-station.jsx`
- **Added** `hlsfSnapshot` to telemetry state and **added** `applyHLSFSnapshot`
  so live `hlsf_snapshot` bridge events now update Dock telemetry instead of being ignored
- **Updated** `handleBridgeMessage`: now handles `hlsf_snapshot`
- **Replaced** the first-pass HLSF canvas with projected live-field rendering:
  - current HLSF position dot from `snapshot.position`
  - top 3 active dimensions rendered from `snapshot.active_dims`
  - hysteresis boundary ring from `snapshot.hysteresis`
  - semantic region tag from `snapshot.semantic_tag`
- **Updated** `OrbRegistryPanel`: polls registry every 15s and auto-highlights
  the current `instanceId` as active

#### Verification
- Rebuilt `electron/src/ui/orb-dock-station.bundle.js` successfully with esbuild after wiring changes

#### `electron/src/ui/orb-dock-station.jsx`
- **Added** to `INITIAL_TELEMETRY`: `fourMind`, `fieldDensity`, `epistemicAlignment`,
  `spatialCoord`, `driftDetected`
- **Updated** `applyCognitivePulse`: now captures all HLSF fields from `cognitive_pulse`
  events (`four_mind`, `field_density`, `epistemic_alignment`, `spatial_coordinate`,
  `drift_detected`) — previously these were dropped silently
- **Added** `HLSFFieldView` canvas component: 300×300 canvas showing
  — 4 epistemic mind arms (CALEON/KAYGEE/CALI-X/EMPIRICAL), length = confidence
  — Field density outer ring, opacity scales with density
  — Center core pulse = epistemic alignment
  — Spatial coord dot (yellow) = HLSF node position
  — Drift state changes core glow to red
  — MIND_LABELS, MIND_COLORS, MIND_ORDER constants
- **Added** `OrbRegistryPanel` component: reads `getMeshRegistry()` IPC, renders
  each registered Orb as a selectable row with online/offline indicator
- **Updated** ORB tab: shows `OrbRegistryPanel` ("Connected Orbs" panel at top),
  then Observatory with both `OrbDiagram` (PRESENCE) and `HLSFFieldView` (HLSF FIELD)
  side by side

#### `electron/main/main.js`
- **Added** `orb:mesh-registry` IPC handler: reads `orb_registry.json` from
  `ORB_SHARED_MESH_ROOT/manifests/`, resolves WSL paths to Windows paths,
  checks `heartbeat.json` mtime (< 5 min = online) per Orb

#### `electron/main/preload.js`
- **Added** `getMeshRegistry: () => ipcRenderer.invoke('orb:mesh-registry')`

#### `electron/src/floating_assistant_orb.py`
- **Added** `_write_mesh_heartbeat()`: writes `heartbeat.json` to
  `{ORB_SHARED_MESH_ROOT}/exports/{instance_id}/state_snapshots/`
- **Added** `_heartbeat_loop()`: calls heartbeat write every 60s
- **Updated** `start()`: writes initial heartbeat on startup, starts heartbeat thread

---

## Session: 2026-04-18 | claude-sonnet-4-6 | VSCode/Windows

### Handoff Signature
```
Substrate:  r:\Orb_Assistant_Desktop
Document:   ORB_PRODUCT_ECOSYSTEM.md (created this session)
JSX lines:  1393 (down from 1487 — old monolithic layout removed)
Bundle:     src/ui/orb-dock-station.bundle.js — 1.1mb, clean build
Branch:     main | e76246b
```

### Changes This Session

#### `electron/src/ui/orb-dock-station.jsx`
- **Removed** old monolithic single-page layout (level 1/2/3 view buttons, three-column
  panel grid, inline Studio iframe all on one page)
- **Removed** stale state vars: `skinStudioTabId`, `skinStudioFrameNonce`,
  `skinStudioFrameState`, `windowLabel`, `processLabel`, `meshRootLabel`, `controllerLabel`
- **Added** three-tier tabbed layout:
  - Header: orb pulse dot + "ORB DOCK" + TIER N | tab nav (ORB/RUNTIME/SETTINGS) |
    Studio button (tier≥3) + Dock/Launch button + clock
  - ORB tab: Orb Observatory (OrbDiagram + DockedOrbMirror) + ChatPanel
  - RUNTIME tab: Core System + Orb Stats (2-col grid) + Live Runtime pills + Latency
    sparkline + Event Feed
  - SETTINGS tab: LLM Connector + Orb Skin selector + Voice toggle
  - Status bar (pinned bottom, 32px): DEVICE | LATENCY | ANOMALIES | INTERACTIONS |
    LISTEN toggle
- **Added** `OrbStudio` component: consistent dark styling, tab nav (first 6 Studio tabs),
  full-height iframe, status bar, Reload button
- **Updated** root render: detects `?view=studio` query param → renders OrbStudio,
  otherwise OrbDockStation
- **Updated** `tier` source: reads from `?tier=N` URL query param (set by main.js)
  instead of local state

#### `electron/main/main.js`
- **Added** `let studioWindow = null`
- **Updated** `openDockStationWindow()`: reads `ORB_DOCK_TIER` env var, sets
  tier-appropriate window dimensions (Tier 1: 480×740, Tier 2+: 860×860),
  passes `?tier=N` query param to loadFile
- **Added** `openStudioWindow()`: creates 1280×900 BrowserWindow, loads dock HTML
  with `?view=studio`, sends `orb:studio-connected` / `orb:studio-closed` events
  to dock window on open/close
- **Added** IPC handler `orb:open-studio` → calls `openStudioWindow()`

#### `electron/main/preload.js`
- **Added** `openStudio: () => ipcRenderer.invoke('orb:open-studio')`
- **Added** `onStudioConnected`, `onStudioClosed` event subscriptions

#### `electron/src/cali_skg.py` *(previous session, confirmed)*
- `torch` bound at module level after conditional import (fixes DEVICE: unknown)
- `llm_*` keys added to `self.orb_state` initial dict

#### `electron/src/floating_assistant_orb.py` *(previous session, confirmed)*
- `_query_local_llm()` method added (OpenAI-compatible endpoint POST)
- `reason_with_cali()` routes via local LLM when `llm_route == "local"`

### New Documents Created
- `r:\Orb_Assistant_Desktop\ORB_PRODUCT_ECOSYSTEM.md` — product tier definition,
  addon model, mesh configuration examples including enterprise (22–25 Orb) scenario
- `r:\Orb_Assistant_Desktop\SESSION_NOTES.md` — this file

### Architecture Decisions Made
- **Substrate vs Product**: `r:/Orb_Assistant_Desktop` is Bryan's personal dev
  substrate. Production Orbs are separate independent deployments fashioned from it.
  Bryan's mesh entries (wsl/desktop/web) are his dev instances, not product categories.
- **Dock Station is generic**: reads whatever `orb_registry.json` is in the configured
  mesh root. Works for 2 Orbs or 45+. No hardcoded Orb assumptions.
- **Studio is a separate window**: Electron BrowserWindow, same HTML bundle loaded
  with `?view=studio`. Consistent styling with Dock, not a browser window.
- **Tier gating via env + URL**: `ORB_DOCK_TIER` env → passed as `?tier=N` →
  read in JSX to show/hide tabs and Studio button.
- **EGF disabled by default**: `ORB_ENABLE_EGF_TENSOR` not set. HLSF always active
  via `hlsf_singleton`. EGF requires torch + explicit opt-in.

### Pending / Next
- [ ] Wire HLSF + EGF field data into OrbDiagram (real cognitive visualization —
      `four_mind`, `field_density`, `spatial_coordinate`, `epistemic_alignment`
      from `cognitive_pulse` events not yet captured in useTelemetry)
- [ ] Orb registry panel in Dock ORB tab (reads `orb_registry.json` from mesh,
      shows connected Orbs, allows switching active Orb)
- [ ] Mesh heartbeat / online status per Orb (check exports directory for fresh
      status artifact)
- [ ] `ORB_PRODUCT_ECOSYSTEM.md` — add pricing, licensing/activation mechanism,
      mesh write path spec for Website and Browser Orbs
- [ ] Swarm task format spec

---

## Session: 2026-04-29 | Desktop ORB monitor traversal + comms repair

### Changes This Session
#### `electron/main/main.js`
- Added virtual display rectangle metadata for multi-monitor ORB traversal.
- Forwarded `displayRects` through `orb:position-update`.
- Fixed Dock/desktop chat extraction to accept Python bridge `response_text`.

#### `electron/src/orb-renderer.js`
- Added deterministic multi-display patrol.
- ORB now receives monitor bounds and periodically targets each display instead of drifting around the virtual desktop center.

#### `orb-instance.local.ps1`
- Enabled `ORB_MULTI_DISPLAY_PATROL=1`.
- Set patrol interval and traversal speed bonus.

### Live Validation
- Restarted Desktop ORB after patch.
- Heartbeat refreshed at `R:\orb_mesh\exports\desktop\state_snapshots\heartbeat.json`.
- Direct Python bridge query returned `query_result`, proving bridge stdin/stdout comms are functional.
- `127.0.0.1:11434` is not currently serving Ollama/Qwen, so local LLM-backed responses require starting or installing the local model server.

---

## Session: 2026-04-29 | Dock Station readability pass

### Changes This Session
#### `electron/src/ui/orb-dock-station-substrate.js`
- Increased substrate Dock font sizes for tabs, panels, pills, paths, services, and footer.
- Replaced harsh cyan-heavy palette with softer off-white text, muted labels, green status, and amber warning values.
- Reworked Services tab from equal two-column debug panels to a denser services/results layout.
- Reduced visual noise in service action buttons by making Status primary and Stop quiet-danger.

#### `electron/src/ui/orb-dock-station.jsx`
- Increased main Dock panel, pill, header, chat, input, button, and footer type sizes.
- Reduced Talk to ORB panel height and improved chat message contrast/line height.
- Changed footer status label from `DEVICE` to `COGNITION` so it is less misleading than a generic CPU/GPU claim.
- Rebuilt `electron/src/ui/orb-dock-station.bundle.js`.

### Live Validation
- `node --check electron/src/ui/orb-dock-station-substrate.js` passed.
- React Dock bundle rebuilt with esbuild.
- Desktop ORB restarted and heartbeat refreshed.

---

## Session Template (copy for next session)

```
## Session: YYYY-MM-DD | model | seat

### Handoff Signature
\```
Substrate:
Document:
JSX lines:
Bundle:
Branch:
\```

### Changes This Session
#### file/path
- change

### Architecture Decisions Made
-

### Pending / Next
- [ ]
```

---

## Session: 2026-05-24 | GPT-5 Codex | Windows/PowerShell

### Handoff Signature
```
Substrate:  R:\R_Drive_Substrate\Orb_Assistant_Desktop
Focus:      ORB bridge exit(code=1) + dock visual tuning
Entry cmd:  cd R:\R_Drive_Substrate\Orb_Assistant_Desktop\electron\.orb-assistant && npm run dev
Changed:    electron/main/orb-bridge.js
            electron/src/ui/orb-dock-station.jsx
            electron/src/ui/orb-dock-station.bundle.js
```

### Changes This Session
#### `electron/main/orb-bridge.js`
- Updated Python path resolution order on Windows to prefer:
  - `R:\R_Drive_Substrate\Services\qwen_tts_312\Scripts\python.exe`
  - then local app Python installs.
- Added stderr ring buffer and appended `stderr_tail` to bridge exit errors so repeated `Orb process exited (code=1)` now carries root-cause context.

#### `electron/src/ui/orb-dock-station.jsx`
- Slowed pulse animation and increased visible opacity for dock pulse indicator.

#### `electron/src/ui/orb-dock-station.bundle.js`
- Mirrored the same pulse tuning so runtime matches source in current dev flow.

### Runtime Notes
- Direct run of `electron/src/floating_assistant_orb.py` in this session produced `ready` and heartbeat output under current shell context.
- Electron logs still indicate intermittent ORB bridge exits in user run path; next actionable debug data is now available in `stderr_tail` from patched bridge errors.
- GPU state transitions from disabled at boot to enabled after startup are observed and not the immediate blocker.

### Next Immediate Step
- Restart with entry command above, reproduce once, then capture the full `orb:set-state` (or `orb:set-listening`) error including `stderr_tail` and patch the named Python dependency/import failure directly.

---

## Session: 2026-05-24 | GPT-5 Codex | ORB movement discipline refactor

### Handoff Signature
```
Substrate:  R:\R_Drive_Substrate\Orb_Assistant_Desktop
Focus:      Companion intent + field motion wiring
Changed:    electron/src/orb-renderer.js
            electron/src/interface/companion_intent.js
            electron/src/hlsf_geometry/field_motion.js
```

### Changes This Session
#### `electron/src/interface/companion_intent.js`
- Added centralized semantic movement authority (`CompanionIntent`).
- Intent decides state (`calm_idle`, `aware`, `searching`, `thinking`, `returning`, `concerned_degraded`).
- Added intent telemetry logging (`[COMPANION_INTENT]`) for movement authority visibility.
- Playfulness is configurable and currently disabled by default.

#### `electron/src/hlsf_geometry/field_motion.js`
- Added motion execution layer (`FieldMotion`) with velocity, acceleration capping, damping, and bounded motion output.
- Layer receives semantic intent profile + target zone and outputs pose/velocity/field-state.

#### `electron/src/orb-renderer.js`
- Wired renderer loop to use `CompanionIntent` + `FieldMotion` as movement pipeline.
- Removed direct playful/re-anchor movement branches from the animation loop.
- Kept monitor bounds and multi-display patrol behavior, but routed resulting target through field motion.
- Set cursor-follow default to opt-in (`ORB_CURSOR_FOLLOW=1`) instead of implicit on.
- Set playful behavior default to opt-in (`ORB_PLAYFUL_IDLE_ENABLED=1`) instead of implicit on.

### Verification
- `node --check src/interface/companion_intent.js` passed.
- `node --check src/hlsf_geometry/field_motion.js` passed.
- `node --check src/orb-renderer.js` passed.

### Notes


## Session: 2026-05-25 | GPT-5 Codex | Conversation Proof Lane

### Scope
- No memory system redesign.
- No vault routing refactor.
- No multi-agent/UI architecture changes.
- Added only a minimal conversation-proof writer in the existing chat loop.

### Changes
- `electron/main/main.js`
  - Added `shouldPersistConversationProof(prompt)`.
  - Added `writeConversationProofRecord(...)`.
  - Hooked proof recording into `ipcMain.handle('orb:chat', ...)` for pass/fail outcomes.
  - Record outputs:
    - `CALI_System/memory/conversation_tests/*.json`
    - `CALI_System/notes/conversation_tests/*.md`
  - Record fields include: timestamp, user_prompt, orb_response, provider, model, voice_played, test_type, status, error.

### Validation
- `node --check electron/main/main.js` passed.

## Session: 2026-05-25 | GPT-5 Codex | Voice Routing Correction (Qwen primary)

### Scope
- Patch-only from voice audit findings.
- No broad voice system redesign.
- No UI/memory refactor outside conversation-proof schema extension.

### Files changed
- `electron/src/floating_assistant_orb.py`
- `electron/src/cali_skg.py`
- `electron/main/main.js`
- `orb-instance.local.ps1`

### Applied corrections
- Qwen TTS bridge set as primary/default route in runtime `speak()`.
- Kokoro retained as fallback-only route.
- Edge fallback removed from `cali_skg.py` voice config.
- Qwen response normalization now resolves to `audio_path` (direct path fields or base64 decode to `CALI_System/voice_cache`).
- Added provider-chain metadata on voice payload + query/research responses:
  - `cp3_invoked`
  - `tts_provider`
  - `tts_fallback_used`
  - `qwen_tts_endpoint`
  - `audio_path`
  - `audio_played`
  - `audio_error`
- Conversation proof record schema expanded to include llm + voice chain contract and statuses:
  - `passed_text_and_audio`
  - `partial_success_text_only`
  - `failed`

### Validation
- `node --check electron/main/main.js` passed.
- `python3 -m py_compile` passed for:
  - `electron/src/floating_assistant_orb.py`
  - `electron/src/cali_skg.py`

## Session: 2026-05-25 | Codex | Prime swarm lineage normalization
- Patched electron/src/orb-renderer.js with deterministic prime lineage resolver (
esolvePrimeSwarmLineage).
- Runtime now normalizes any requested swarm count to canonical set [2,3,5,7,11] and records 
equestedCount, 
esolvedCount, 
ormalized, 
equestedPrime, and lineageToken.
- Added mission-level lineage telemetry ([SWARM_LINEAGE]) on dispatch and return, keyed by missionId, preserving canonical audit context without changing Dock or voice routing.

- 2026-05-25: Dock startup layout normalized to keep control buttons on-page at open (wrapped rows + responsive header width in electron/src/ui/orb-dock-station.jsx).
- Manual Morb count is now unbounded numeric input; requested values are prime-normalized (next prime >= 2) before dispatch to runtime.
- Updated diagnostics deploy color to cyan-family and rebuilt electron/src/ui/orb-dock-station.bundle.js.
- 2026-05-25: Swarm animation now honors numeric orb-count requests found in query text when no explicit count payload is present; count is still prime-normalized in runtime. Diagnostics outbound color set to red; research outbound remains blue; success return remains green.
- 2026-05-25: Canonical prime policy enforced again. Swarm counts now normalize strictly to approved set [2,3,5,7,11] across Dock manual input and renderer runtime (including query-derived numeric requests).
- 2026-05-25: Added STRICT_COHERENCE lock in docs (README.md, ORB_SWARM_AUDIT_DOCTRINE.md) for Prime ORB swarm cardinality. Canonical set is fixed to [2,3,5,7,11]; all count inputs must normalize to this set; non-canonical deployment is an audit fault.
- 2026-05-25: LLM/TTS connectivity alignment patch. Active local services observed: Ollama on 11434, Qwen bridge on 8003. Updated orb-instance.local.ps1 and electron/src/floating_assistant_orb.py default Qwen endpoint to http://127.0.0.1:8003 to resolve VOICE READY false due to stale 8020 config.
- 2026-05-25: Dock status truth patch for connection pills. local_llm now includes live probe (
eady, status_code, error) from backend /api/tags check; Dock now uses local_llm.ready as primary signal for LLM CONNECTED and retains existing Qwen voice probe path for VOICE READY.
- 2026-05-25: Voice connectivity truth patch. Restored Qwen endpoint default to 8020 and require synthesis-route capability for voice-ready.
- 2026-05-25: Implemented manifest-backed DockStation service controls and monitoring. Manifest: CALI_System/core_knowledge/spruked/services.json. Services tab now uses real status/open/start/stop behavior with truthful not-configured handling and last-service audit details (service/action/result/timestamp/status_code/error). Memory tab now shows configured substrate paths including CALI system, memory, notes, voice cache, and logs with existence indicators.
- 2026-05-25: Dock chat now plays ORB speech immediately from speak_result bridge events (even when fallback TTS is produced outside the initial chat payload), with audio-path dedupe to avoid duplicate playback.
- 2026-05-25: Dock disconnected/chat no-response fix. Removed blocking per-service command execution and per-poll network health fan-out from bridge status path. Services now cache status for polling and perform full probes on explicit actions.
- 2026-05-25: Added one-shot Dock startup connect behavior to mirror Activate button. On mount: orb visible -> activate command -> local LLM auto-apply (when local route).
- 2026-05-25: Added fast-fail Qwen TTS gating to keep chat responsive when voice is offline (_probe_qwen_tts_health gate + shorter synth timeout).

## 2026-05-25 14:34:38 -05:00 | Dock Station runtime truth snapshot + recorder
- Added backend runtime_snapshot in electron/src/floating_assistant_orb.py for Dock runtime truth: channel, controller, presence, listening, LLM, governance, encoder, voice, Qwen/Kokoro, UCM-disabled state, interactions, anomalies, confidence, success rate, and timestamp.
- Added local Dock Talk transaction JSONL recorder in electron/main/main.js at CALI_System/runtime_logs/dock_transactions.jsonl.
- Dock runtime panel now prefers runtime_snapshot and no longer lets pending status polls overwrite live state with misleading STARTING/DISCONNECTED defaults.
- Bottom channel label now separates channel connectivity from listening state: CHANNEL CONNECTED / LISTENING OFF is distinct from disconnected.
- Voice display now uses explicit states: QWEN ACTIVE, KOKORO FALLBACK, VOICE DEGRADED, or NO VOICE.
- UCM remains disabled unless ORB_ENABLE_UCM_STATUS_CHECK=1; no UCM reconnect was added.
- Kokoro fallback remains intact.
- Validation run: python -m py_compile electron/src/floating_assistant_orb.py, 
ode --check electron/main/main.js, and Dock bundle rebuild via 
px esbuild ...orb-dock-station.jsx passed.
- Live Electron restart is required for the running Dock to load these changed source/bundle files.


## 2026-05-25 15:11:28 -05:00 | Electron clean restart hotfix
- Stopped stale Electron/Node/ORB Python child processes only; preserved Qwen bridge/backend listeners on 8020/8031.
- Cleared Electron .orb-assistant\Network cache; .orb-assistant\Cache was absent.
- Restarted Electron with 
pm start and ORB_OPEN_DOCK_ON_START=1; no inspector 9229 listener and no Network/cache access-denied startup errors observed.
- Patched Dock z-order so Dock Station stays above fullscreen ORB overlay windows while moving across monitors.
- Patched set_orb_state handler to return a minimal state instead of calling heavy get_status(), preventing orb_state_result timeouts from that path.
- Remaining: Dock Talk transaction did not advance from UI automation; latest recorder line still shows prior Timed out waiting for query_result.

## 2026-05-25 15:15:59 -05:00 | Dock Talk timeout fix
- Removed blocking voice synthesis from normal query_result path in electron/src/floating_assistant_orb.py; set ORB_INLINE_QUERY_VOICE=1 only if synchronous query voice is explicitly wanted.
- Replaced heavy orb.get_status() inside query_result with minimal state so Dock Talk text returns before status/voice probes.
- Increased speakOrb timeout in electron/main/orb-bridge.js to ORB_SPEAK_TIMEOUT_MS default 120000 so slow Qwen speech can still return as speak_result.
- Validation passed: Python compile and orb-bridge JS check.

## 2026-05-25 15:22:18 -05:00 | LLM endpoint normalization
- Normalized ORB local LLM endpoint to strip /api/generate or /api/tags before health/query calls; fixes false LLM disconnected when stored endpoint included an API route.


## 2026-05-25 15:24:19 -05:00 | Windows LLM endpoint coercion
- Coerced stale Windows-side wsl.localhost Ollama endpoint to 127.0.0.1 so Dock LLM health matches the confirmed live local service.


## 2026-05-25 15:30:44 -05:00 | Minimal spine mode
- Added ORB_MINIMAL_SPINE_MODE=1 to orb-instance.local.ps1 with UCM and speech recognition disabled.
- Added 
eason_with_local_llm_only() in loating_assistant_orb.py; it calls only local Ollama/Qwen at 127.0.0.1:11434 / qwen2.5:3b.
- Query handler now short-circuits in minimal mode: returns query_result first with minimal_spine=true, 
easoning_provider=llm, oice_provider=qwen, 	ts_provider=qwen, 	ts_fallback_used=false, then emits Qwen speech after the result.
- Validation passed: Python compile and JS checks.

## 2026-05-25 15:32:33 -05:00 | Minimal spine microphone one-shot
- Re-enabled ORB_ENABLE_SPEECH_RECOGNITION=1 so the Dock microphone button can use one-shot capture while ORB_MINIMAL_SPINE_MODE remains active and UCM/auto-listen remain disabled.


## 2026-05-25 15:37:48 -05:00 | Dock microphone event bridge
- Fixed Dock mic transcript path: Python emits speech_heard; main now forwards that as orb:speech-pulse with transcript/transcription fields so Dock input fills correctly.
- Increased ORB_LISTEN_ONCE_TIMEOUT_MS to 60000 for one-shot microphone capture.


## 2026-05-25 15:38:32 -05:00 | Minimal spine governance bypass
- Set ORB_LLM_GOVERNANCE_WRAPPER=0 and added ORB_LLM_ENDPOINT/ORB_LLM_MODEL direct Ollama vars in orb-instance.local.ps1.
- Runtime snapshot reports governance_wrapper=off whenever ORB_MINIMAL_SPINE_MODE=1.


## 2026-05-25 15:40:37 -05:00 | Minimal spine Qwen-only voice
- In ORB_MINIMAL_SPINE_MODE, speak() no longer calls Kokoro fallback. Qwen TTS is the only voice path; failure reports qwen_no_audio_path/audio_error and stays silent.
- build_voice_payload skips CALI voice_package in minimal spine so ACP3/CALI packaging is not part of the direct LLM -> Qwen TTS lane.


## 2026-05-25 15:45:06 -05:00 | Normal mode restored before token cutoff
- Reverted the minimal-spine experiment: removed ORB_MINIMAL_SPINE_MODE, restored ORB_LLM_GOVERNANCE_WRAPPER=1, restored normal query routing, restored CALI voice_package, restored Kokoro fallback after Qwen failure.
- Kept Dock/mic event bridge fix: speech_heard is forwarded as orb:speech-pulse so the Dock mic transcript can populate the input.
- Restarted Electron with restored normal env. Dock Station is visible.
- Confirmed live listeners: Qwen bridge 8020 PID 632, Qwen CustomVoice backend 8031 PID 17304, Ollama 11434 PID 3464.
- No 9229 inspector listener shown in final port check.

## 2026-05-25 15:48:39 -05:00 | Final session handoff
- Final runtime mode restored to normal ORB mode after the minimal-spine experiment.
- Governance wrapper is restored on via ORB_LLM_GOVERNANCE_WRAPPER=1.
- Kokoro fallback is restored behind Qwen TTS; CALI voice packaging is restored.
- Kept useful fixes: Dock runtime snapshot, Dock transaction recorder, Dock z-order over ORB overlay, minimal orb_state_result, and speech_heard -> orb:speech-pulse forwarding for the Dock mic button.
- Final confirmed live services from this session: Qwen bridge 127.0.0.1:8020, Qwen CustomVoice backend 127.0.0.1:8031, Ollama 127.0.0.1:11434, and visible Dock Station.
- Main remaining known issue: normal query path can still be slowed by full ORB/CALI/voice/status layers; safest next pass is one focused query_result latency test, not another broad refactor.

## 9:30 PM Resume Point - 2026-05-31 19:28:10

Stop reason: usage budget dropped to ~2%; do not run broad scans when resuming.

Current project: R:\R_Drive_Substrate\Orb_Assistant_Desktop / DockStation + floating ORB.

What was changed before stop:
- electron/src/orb-renderer.js: emergency cursor-leash fix. Autonomous ORB should not chase cursor or clamp to cursor monitor; cursor is only avoidance/guided signal.
- electron/main/main.js: launch authority split started; generic setOrbVisibility(true) is blocked and dedicated orb:launch-from-dock path was added. Tray cleanup partially patched with destroyTray().
- electron/main/preload.js: exposed launchOrbFromDock().
- electron/src/ui/orb-dock-station.jsx: Launch / Activate buttons changed to call launchOrbFromDock().
- electron/src/ui/orb-dock-station.bundle.js: bundle was rebuilt before later main patches, but may need rebuild again after final UI changes.
- electron/src/ui/orb-dock-station-substrate.js: removed bootstrap auto-call to setOrbVisibility(true).

Verified before stop:
- 
ode --check electron/main/main.js, electron/main/preload.js, and electron/src/orb-renderer.js passed at that point.
- Readiness returned 200 on http://127.0.0.1:21100/api/v1/readiness during prior checks.
- Visible pre-launch ORB check previously returned VISIBLE_CALEON_ORB_COUNT=0.

Known unresolved:
- DockStation Launch ORB / Activate ORB still reported by user as not launching the visible ORB.
- EGF dock display/cognition wiring was requested but not completed.
- System tray may show stale ORB icons from prior forced-killed Electron instances; patch started but needs clean verification.
- Do not resume EGF work until Launch / Activate is fixed.

Resume rule:
- No broad scans.
- Fix one thing only: Launch / Activate.
- Inspect only: electron/main/main.js, electron/main/preload.js, electron/src/ui/orb-dock-station.jsx, electron/src/orb-renderer.js.
- Verify only: DockStation button -> preload -> main IPC -> ORB BrowserWindow -> visible Caleon Orb after click, and zero Caleon Orb before click.

Low-token resume prompt:
Fix Launch / Activate only. No broad scans. Inspect only main.js, preload.js, orb-dock-station.jsx, orb-renderer.js. Make DockStation button launch the ORB BrowserWindow and verify visible Caleon Orb appears only after click.
"@
 = @"

[2026-05-31 19:28:10] 9:30 PM RESUME HANDOFF
- Usage budget dropped to ~2%; stopped active debugging.
- Cursor tether fix applied in electron/src/orb-renderer.js.
- Launch authority split partially applied: orb:launch-from-dock added; generic setOrbVisibility(true) blocked.
- Preload exposes launchOrbFromDock(); DockStation buttons call it.
- Tray cleanup partially patched in electron/main/main.js.
- User reports Launch / Activate still does not launch ORB. This is next and only priority.
- EGF dock cognition monitor requested but not implemented; defer until launch works.
- Next pass must avoid broad scans and inspect only main/preload/dock-station/orb-renderer.
