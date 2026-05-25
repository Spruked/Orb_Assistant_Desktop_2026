# CALI Floating Assistant Orb

An Electron + Python desktop orb for CALI/Caleon experiments. The current build is a transparent overlay shell with a live Python bridge, local skin vault, tray docking controls, and first-pass swarm visuals.

## Current Build

What is working in this repo now:
- Two-way Electron-to-Python JSON bridge through `stdin`/`stdout`
- Full-field transparent orb shell loaded from `src/orb-shell.html`
- Live renderer updates from Python events such as `ready`, `cognitive_pulse`, and hysteresis
- Tray-based dock/launch controls plus verbal visibility commands on the Python side
- Integrated Dock Station opened from the tray and wired to live IPC/status/bridge telemetry
- Dock Station substrate extension for CALI memory, ACP I/O, research vault, skills, notes, and service domain status
- Local-first skin ingestion into `.orb-assistant/skins` served through `orb-skin://`
- First `zip-and-absorb` swarm animation pass in the renderer

What is still partial:
- `space_field` is not available, so the Epistemic Gravity Field layer is offline
- UCM status probing currently fails when nothing is listening on `localhost:5050`
- Service launch/status controls for the website ecosystem still need explicit local manifests
- On this development machine, monitor flicker appears more likely tied to the Windows display stack (`DisplayLink` / old Intel graphics driver / mixed cabling) than to a recent app-level GPU reset pattern

## Run

Prerequisites:
- Node.js 16+
- Python 3.8+
- The Python environment used by `main/orb-bridge.js`

Install:

```bash
npm install
```

Start the orb:

```bash
npm start
```

Notes:
- The `start` script explicitly unsets `ELECTRON_RUN_AS_NODE` before launching Electron.
- This repo does not currently use `npm run build` for local development. The active runtime loads the shell directly from `src/orb-shell.html`.
- For sovereign instance launches, use `npm run start:instance` with a repo-root `.orb-instance.env`.

## Sovereign Instances

This runtime now supports multiple sovereign ORB identities through environment variables.

Key vars:
- `ORB_INSTANCE_ID` separates the runtime identity such as `wsl` or `desktop`
- `ORB_PRODUCT_NAME` changes the visible product identity
- `ORB_APP_ID` separates packaged/runtime app identity
- `ORB_USER_DATA_DIR` separates Electron user data and skin vaults
- `ORB_SYSTEM_ROOT` separates CALI system state and local memory
- `ORB_SHARED_MESH_ROOT` points both ORBs at the same shared mesh
- `ORB_SINGLE_INSTANCE=0` allows sovereign instances to coexist
- `ORB_PYTHON_PATH` overrides the Python runtime used by the bridge

Files:
- Example env file at [.orb-instance.env.example](/home/bryan/spruked.com/Orb_Assistant/.orb-instance.env.example)
- Generic launcher at [launch_orb_instance.sh](/home/bryan/spruked.com/Orb_Assistant/scripts/launch_orb_instance.sh)
- Provisioner for the R-drive desktop ORB at [provision_sovereign_orb.py](/home/bryan/spruked.com/Orb_Assistant/scripts/provision_sovereign_orb.py)

## Architecture

Primary runtime pieces:

1. Python orb runtime in [src/floating_assistant_orb.py](/home/bryan/spruked.com/Orb_Assistant/electron/src/floating_assistant_orb.py)
2. Electron bridge and window manager in [main/orb-bridge.js](/home/bryan/spruked.com/Orb_Assistant/electron/main/orb-bridge.js) and [main/main.js](/home/bryan/spruked.com/Orb_Assistant/electron/main/main.js)
3. Renderer shell in [src/orb-shell.html](/home/bryan/spruked.com/Orb_Assistant/electron/src/orb-shell.html) and [src/orb-renderer.js](/home/bryan/spruked.com/Orb_Assistant/electron/src/orb-renderer.js)
4. Dock Station in [src/ui/orb-dock-station.html](/home/bryan/spruked.com/Orb_Assistant/electron/src/ui/orb-dock-station.html), [src/ui/orb-dock-station.bundle.js](/home/bryan/spruked.com/Orb_Assistant/electron/src/ui/orb-dock-station.bundle.js), and [src/ui/orb-dock-station-substrate.js](/home/bryan/spruked.com/Orb_Assistant/electron/src/ui/orb-dock-station-substrate.js)

Current flow:

```text
Python runtime -> JSON lines over stdout/stderr -> Electron main -> preload bridge -> React orb shell
Renderer actions -> preload bridge -> Electron main -> JSON commands over stdin -> Python runtime
Local image drop/path -> ingest_skin.py -> .orb-assistant/skins -> orb-skin:// -> renderer core skin
Dock Station -> preload bridge -> Electron main -> Python status/research/skill memory -> live operator panels
```

## Key Files

```text
main/
  main.js              Electron window, tray, IPC, topmost behavior, local protocol
  preload.js           Renderer-safe API surface
  orb-bridge.js        Python process lifecycle and JSON bridge
src/
  floating_assistant_orb.py  Python runtime
  orb-shell.html             Transparent shell entry
  orb-renderer.js            React orb UI, swarm, skin, bridge state
  ui/orb-dock-station.html   Dock Station entry
  ui/orb-dock-station.bundle.js  Bundled Dock Station UI
  ui/orb-dock-station-substrate.js  Live substrate/ACP/research/skills extension
  ingest_skin.py             Local-first skin ingestion utility
.orb-assistant/
  skins/                     Local vault for image skins
  skins/metadata/            Metadata sidecars for vaulted skins
```

## Desktop Workflow Notes

- The user prefers timestamped continuity notes and restart-friendly summaries.
- Session record for this build thread lives in [SESSION_RECORD_2026-03-18_212816_CDT.md](/home/bryan/spruked.com/Orb_Assistant/electron/SESSION_RECORD_2026-03-18_212816_CDT.md).
- The active Dock Station is integrated in this Electron app and opens from the system tray.

## Next Technical Steps

- Add explicit local service manifests for the website ecosystem
- Formalize a Dock Station bundle rebuild script
- Smooth or throttle high-volume `cognitive_pulse` traffic so the orb feels less twitchy
- Improve the visual "inside glass" effect with a stronger outer shell and specular layers
- Make orb scale responsive to display work-area size and typical NFT art proportions

## Dock Runtime Truth Layer (2026-05-25)

Dock Station is treated as the operator cockpit and black-box recorder. The backend now emits a single runtime_snapshot consumed by the Dock runtime panel, and Dock Talk transactions append to CALI_System/runtime_logs/dock_transactions.jsonl.

The panel distinguishes Dock channel connectivity from listening state. CHANNEL CONNECTED / LISTENING OFF is valid and no longer appears as disconnected. Voice state is explicit: QWEN ACTIVE, KOKORO FALLBACK, VOICE DEGRADED, or NO VOICE.

UCM remains opt-in through ORB_ENABLE_UCM_STATUS_CHECK=1; Kokoro fallback remains available behind Qwen.

