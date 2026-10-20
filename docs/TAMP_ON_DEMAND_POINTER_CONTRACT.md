# TAMP On-Demand Pointer Contract

Desktop ORB pointing is not sitemap navigation. It is an on-demand task-and-motion planning loop over the current desktop state.

The pointer stack must resolve a human or cognition request like "point at the GPU process", "show me that error", or "where is the checkout button" into a visible target, a coordinate frame, and a safe pointer action.

## Ownership

| Layer | Owner | Responsibility |
| --- | --- | --- |
| Perception/capture | Desktop ORB MCP or Orb Weaver | Current screen/capture and visible object extraction |
| Interpretation | TPC/TAMP planner | Decide what target should be pointed at now |
| Coordinate mapping | Desktop ORB pointer runtime | Convert target to virtual desktop x/y and monitor id |
| Motion | Desktop ORB renderer | Move ORB/pointing affordance calmly to target |
| Action escalation | Desktop ORB MCP | Gate click/open/select behind operator approval |

## Existing Pointer Surface

```text
R:\Orb_Assistant_Desktop\mcp\orb_desktop_mcp\orb_pointer
```

Runtime folders:

```text
captures\  Current screenshots, OCR/object extraction, and visible UI observations.
state\     Current display map, cursor state, active target, and pointer planner state.
actions\   Resolved pointer actions for Desktop ORB to consume.
baseline_maps\  Fallback reference maps for recovery orientation only.
```

Baseline maps are governed by:

```text
R:\Orb_Assistant_Desktop\docs\BASELINE_REFERENCE_MAPS_CONTRACT.md
```

Live perception snapshots are governed by:

```text
R:\Orb_Assistant_Desktop\docs\DESKTOP_SCENE_SWEEP_PERCEPTION_CONTRACT.md
R:\Orb_Assistant_Desktop\mcp\orb_desktop_mcp\orb_pointer\observation_snapshot.schema.json
```

## Pointer Modes

Allowed passive/automatic modes:

- `observe`: record or explain a target without moving.
- `hover_context`: point near a target without clicking.
- `point_at`: visually indicate a target on demand.
- `explain`: point while explaining why the target matters.
- `dismiss`: move away from a target or clear pointer focus.

Escalated modes:

- `select`
- `open`
- `operator_override`

Desktop ORB may point automatically. It must not click, open, select, type, or dismiss UI elements with side effects unless the operator approval path accepts it.

## Coordinate Frames

Pointer plots must declare a coordinate frame:

- `virtual_desktop`: coordinates are relative to the Desktop ORB virtual overlay.
- `monitor`: coordinates are relative to a specific monitor.
- `window`: coordinates are relative to a captured application window.
- `capture`: coordinates are relative to a screenshot/capture image.

Desktop ORB renderer uses `virtual_desktop` coordinates. Any other frame must be resolved into `virtual_desktop` before motion.

## On-Demand Pointer Plot

Canonical pointer plot payload:

```json
{
  "id": "pointer-2026-07-28T08-20-00Z-001",
  "source": "voice",
  "intent": "point_at",
  "target": {
    "kind": "visible_text",
    "label": "llama-server.exe",
    "description": "The local llama.cpp server process in Task Manager",
    "selector": null
  },
  "frame": {
    "type": "virtual_desktop",
    "monitor_id": "2904977303",
    "capture_id": null,
    "window_id": null
  },
  "point": {
    "x": 2420,
    "y": 420,
    "monitor_id": "2904977303",
    "timestamp": "2026-07-28T08:20:00Z"
  },
  "bbox": {
    "x": 2380,
    "y": 390,
    "width": 180,
    "height": 34
  },
  "confidence": 0.82,
  "evidence": [
    "OCR match for llama-server.exe",
    "Process row visible in active capture"
  ],
  "metadata": {
    "request": "point at the llama server",
    "planner": "desktop_tamp"
  }
}
```

## TAMP Loop

1. Receive an on-demand target request.
2. Run or reuse the latest Desktop Scene Sweep for the active task area.
3. Extract visible candidates: OCR text, UI Automation elements, DOM elements, visual controls, windows, icons, controls, cursor-relative regions.
4. Rank candidates by request match, display visibility, confidence, and action safety.
5. Produce a pointer plot with target, frame, point, optional bounding box, confidence, and evidence.
6. Resolve the plot into an action:
   - `point` for `point_at`, `hover_context`, `explain`
   - `observe` for low-confidence or passive observations
   - `operator_review` for click/open/select
7. Desktop ORB renderer moves to the virtual desktop target and rests.
8. If speaking, ORB holds still at the current point until speech ends.

## Baseline Map Recovery

Baseline maps are fallback reference maps, not absolute truth and not action plans.

The active operation must use:

```text
observe live environment -> resolve target -> act -> verify
```

If confidence drops or the ORB loses orientation:

```text
consult baseline map -> reconfirm major regions -> rebuild temporary local scene -> re-run TAMP
```

Baseline maps may help recover browser controls, File Explorer panes, Settings regions, and common Windows dialogs. They may not authorize side-effect actions.

## Desktop Scene Sweep

Desktop Scene Sweep, also called Virtual LiDAR Sweep, is the software perception pass that feeds TAMP. It is not physical LiDAR.

The sweep combines:

- screen capture
- monitor and window geometry
- Windows UI Automation
- browser DOM when available
- targeted Tesseract OCR
- visual object recognition
- blocked-region and safe-path detection

The sweep output is an `ObservationSnapshot`. It is temporary, task-scoped, and must avoid personal documents, emails, browser history, passwords, encrypted stores, cloud account content, and financial data.

## Three-Monitor Requirement

Desktop ORB currently uses one virtual overlay over all monitors. Pointer mapping should prefer `virtual_desktop` coordinates.

The display map should include:

```json
{
  "actual_displays": 3,
  "virtual_bounds": { "x": 0, "y": 0, "width": 5120, "height": 1080 },
  "display_rects": [
    { "id": "2904977303", "index": 0, "x": 1920, "y": 0, "width": 1920, "height": 1080 },
    { "id": "1838998144", "index": 1, "x": 3840, "y": 0, "width": 1280, "height": 720 },
    { "id": "605014388", "index": 2, "x": 0, "y": 0, "width": 1920, "height": 1080 }
  ]
}
```

## Safety Rules

- Pointing is allowed without a sitemap.
- Pointer mapping may use current screenshots/captures.
- Pointer mapping must not scan personal documents, email content, browser history, passwords, encrypted stores, cloud account contents, or financial data.
- Pointer plots with side-effect intents must resolve to `operator_review`.
- Low-confidence plots must resolve to `observe`, not click/select.
- Desktop ORB should favor pointing near a target instead of covering it.
- Baseline maps cannot override live observation or failed verification.
