# Audit 2026-10-20 - authorization, endpoints and wiring

Static audit plus read-only port checks. It is not proof of end-to-end function. The Desktop ORB was not
running during the audit.

## Authorization (no verified owner gate exists)

Path: renderer `window.electronAPI` -> `preload.js` -> `ipcMain.handle` (no sender validation) ->
`orb-desktop-mcp-client.js callDesktopMcpTool` (one check: `DESKTOP_AUTHORITY_TOOLS` and the
`desktopActionsEnabled` flag) -> MCP server `call_tool` (safety guard rules only, no authorization).

Open doors, most direct first:
1. Local app windows (`openLocalAppWindow`, Mail/Spruk_Email on 19000, CRM on 21001) load `http://127.0.0.1` pages
   with the full preload. A script served there can call `setDesktopMcpActionsEnabled(true)` and then drive input
   tools. URLs are overridable by `ORB_MAIL_URL` / `ORB_SPRUK_EMAIL_URL` / `ORB_CRM_URL`.
2. `desktopActionsEnabled` is a flag any renderer can flip; it is not an owner check.
3. The orb overlay runs with `nodeIntegration: true`, `contextIsolation: false`, no CSP. It loads no remote
   script today (all scripts local), but anything that reached it would have full Node access.
4. Ungated MCP tools (callable even with actions disabled): `orb_qwen_code_prompt` (runs a coding agent as a
   subprocess, approval mode unverified), `orb_ocr_screen`, `orb_ocr_image` (any path), plus read-only status tools.
5. The safety guard has 5 rules (coordinate bounds, destructive typing, empty type, suspicious URL, long wait);
   `orb_hotkey`, `orb_open_app`, `orb_clipboard_write`, `orb_drag` and the Qwen prompt have none; bounds default to 7680x4320.
6. Also consequential IPC with no owner check: `orb:service-control` (shell start/stop commands),
   `orb:crm-request`, `orb:email-request`, `orb:dispatch-command` (MORB deploy), `orb:ingest-skin`, `orb:open-search`.

Smallest repairs (none applied yet):
strip the preload from local app windows and deny navigation; allowlist (default-deny) the MCP gate including the Qwen
prompt and OCR tools; validate IPC senders in `main.js`; make enabling actions a native main-process owner step;
enforce a per-launch secret on the MCP server; extend safety rules; record accepted/blocked/completed/failed with one
operation id (`command_accepted|completed|failed` are emitted by `OrbCommandRouter._dispatch_with_lifecycle` but
nothing persists them).

## Endpoints and wiring

* IPC: 64 preload entries - 47 wired, 16 partial, 1 unwired. `orb:cursor-move` and `orb:set-motion` are only used by
  UI files that are never loaded (`FloatingOrb.jsx`, `LivingOrb.jsx`, `main.jsx`, `ui/index.html`, `dashboard.html`,
  `settings.html`); cursor data reaches the renderer through `orb:position-update` from the main process.
* Live UI entry points (from `main.js`): `orb-shell.html`, `ui/orb-dock-station.html` (Dock and Studio), local app URL windows, tray.
* Python bridge: 13 message types handled, all with senders; `command_accepted|completed|failed` and `shutdown_ack`
  have no consumer. New: `memory_record`, `memory_recall`, `memory_status`.
* HTTP routes defined in this repo: `api/main.py` (`/api/v1/tribunal`, `/api/v1/health`, port 8000, not running) and
  `scripts/qwen_tts_wsl_proxy.py` (8021, not running). `api/OrbService.js` is orphaned and calls a missing `sendToOrb`.
* Port ownership on 2026-10-20: 21100 (Dock readiness) was another project's API (`cali-personal-api`, returns 401
  on `/api/v1/readiness`); 19000 is the Spruk_Email backend; 8020 is a Qwen TTS bridge (two launchers started, one holds
  the port). The Dock's readiness probe only checks `res.ok`; service tiles treat any status < 500 as reachable, so
  it cannot tell the intended ORB service from another application on the same port.
* Not listening: 9880, 11455, 8021, 8031-8033, 21000, 21001, 8002, 5199, 7700.

## Other findings

* (Historical: the 3D scene described here was removed on 2026-10-20.) * 3D scene: one transparent window spans the whole virtual desktop (3200x1080 here), so the Three.js canvas, a
  transmission material and a galaxy shader are composited at desktop size for a ~236 px body. The legacy CSS orb
  is still in the render tree. Scene metrics (`window.__ORB_THREE_METRICS__`) are produced but never read or logged.
* Dock: `setActiveOrbSkinUrl is not defined` (tier 3) in the 2026-10-19 log.
* Correspondence Engine (`.orb-runtime/correspondence_engine`): predicate extraction and a provenance accessor were
  fixed (tests in its `tests/`); isolated probationary atoms below 0.7 confidence are deleted on the first maintenance
  cycle and explicit contradictions do not create CONTRADICTS edges (characterized, not changed).

## HLSF mirror data provenance (Dock "HLSF MIRROR")

Checked 2026-10-20 against the running ORB (bridge logging on, 45 s window): 21 `hlsf_snapshot` messages, all from the
live engine, sequence strictly increasing, density rising as stimuli arrived, presence tag changing in step.

Path: `HLSFEngine.field_map` -> `OrbLifecycle._build_hlsf_snapshot` (every 2 s) -> bridge `hlsf_snapshot` -> main
`forwardOrbMessage` -> Dock `applyHLSFSnapshot` -> `HLSFMirrorPanel`. The Dock synthesizes nothing.

Fixed in this pass:
* With no engine the snapshot used to carry the configured 800/650 thresholds and the Dock showed them as readings.
  It now reports 0/0, density 0 and `live: false`. Every snapshot has `live`, `source` (`hlsf_engine`, `unavailable`,
  `error`), `reason`, `seq` and `ts`.
* Node labels and coordinates came from Python's per-process salted `hash()`, so they differed on every run despite the
  "deterministic" docstring. They now use a stable SHA-256 hash (tested across `PYTHONHASHSEED` values).
* `EpistemicGravityBridge.get_visual_state()` was called but never defined, so the EGF mirror could only show a fault.
  It now reports `unavailable` (with the reason) or live field stats.

Still true, not changed:
* Coordinates and N/K labels are hash-derived, not an embedding of what the stimulus means: two cursor positions one pixel
  apart land about as far apart as two far-apart ones. The panel shows real engine state, but the geometry carries no spatial
  meaning.
* Density counts distinct stimuli, and every cursor sample carries a jittering velocity, so 50 samples at one spot created
  49 nodes. It tracks activity volume, not distinct places or concepts. The 800/650 edge-cutter thresholds are engine
  constants; the TPC document describes 700/520.
* While the ORB is docked the main process sends no cursor samples (`sampleDesktopCursor` returns unless the overlay is
  visible), so the HLSF is fed by presence, idle and query stimuli only; cursor stimuli start after Launch.
* The Dock cannot yet show a stale feed: that needs a UI change (use `seq`/`ts`) and `esbuild`, which is not installed here,
  to rebuild `orb-dock-station.bundle.js`.

Tests: `electron/src/test_hlsf_snapshot.py` (10).

## Motion wiring (three runtimes)

Before: the state machine's `motion` domain was fed only by cursor processing (`set_motion_target(CURSOR)` then `complete_motion`
on every cursor sample), so it reported "target: cursor, result: success" while the live motion policy avoids the cursor; the renderer
reported nothing to Python and nothing consumed `motion_status`. After: the renderer reports physical motion through a validated IPC channel,
main reports `docked` when no overlay exists, cursor processing is recorded as activity (not a motion target), and each runtime has an independent
summary. Details and the module map: `docs/THREE_RUNTIMES.md`.
