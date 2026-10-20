# Desktop Scene Sweep Perception Contract

The Desktop ORB does not need physical LiDAR for screen navigation. It needs a LiDAR-like software perception pass over the digital workspace.

Canonical name:

```text
Desktop Scene Sweep
```

Allowed alias:

```text
Virtual LiDAR Sweep
```

This sweep observes only the active task area needed for the current request and produces a temporary `ObservationSnapshot` for TAMP planning.

## Perception Stack

```text
Screen capture
-> window and monitor geometry
-> UI Automation evidence
-> browser DOM evidence when available
-> targeted Tesseract OCR
-> visual object recognition
-> scene understanding
-> TAMP planning
```

Each sensor has a distinct role:

- `screen_capture`: current visual environment.
- `window_geometry`: monitor bounds, window bounds, z-order, occlusion.
- `ui_automation`: Windows controls, roles, names, states, supported actions.
- `dom`: browser-page structure when an authorized browser context is available.
- `tesseract`: visible text recognition.
- `visual_object_recognition`: visible object/control classification when DOM/UI Automation are missing or incomplete.
- `tamp`: planning, replanning, safety gating, and verification.

## VisualSceneRecognizer

The `VisualSceneRecognizer` is the perception component that turns pixels and partial metadata into structured visible-object candidates.

Responsibilities:

- detect visible controls and objects
- classify probable object/control type
- attach bounding boxes
- associate nearby OCR text with objects
- estimate whether objects are interactive
- identify blocked, hidden, disabled, loading, or unsafe regions
- combine evidence from OCR, UI Automation, DOM, visual shape, and window context
- emit confidence and evidence for `PointerTargetResolver`

It must identify high-frequency object families such as:

- buttons, checkboxes, sliders, menus, tabs, dialogs, and text fields
- folders, documents, images, shortcuts, drives, and application icons
- browser controls, page cards, forms, shopping carts, and checkout sections
- warning symbols, loading indicators, error banners, permission prompts, and disabled controls
- window boundaries, overlapping windows, popups, and areas blocked by the ORB itself
- visual controls that expose no useful DOM or accessibility metadata

## ObservationSnapshot

The sweep output is an `ObservationSnapshot`.

Minimum fields:

```json
{
  "schema_version": "1.0",
  "snapshot_id": "scene-2026-07-28T09-30-00Z-001",
  "source": "desktop_scene_sweep",
  "scope": "active_task_area",
  "timestamp": "2026-07-28T09:30:00Z",
  "display_map": {
    "virtual_bounds": { "x": 0, "y": 0, "width": 5120, "height": 1080 },
    "display_rects": []
  },
  "active_window": {
    "title": "",
    "process": "",
    "bounds": { "x": 0, "y": 0, "width": 0, "height": 0 }
  },
  "objects": [],
  "blocked_regions": [],
  "cursor": { "x": 0, "y": 0 },
  "orb": { "x": 0, "y": 0, "radius": 0 },
  "confidence": 0.0,
  "evidence": []
}
```

## Visible Object Candidate

Every visible object candidate should be structured:

```json
{
  "id": "obj-001",
  "type": "button",
  "probable_role": "browser_download",
  "visible_text": "Download",
  "application": "Chrome",
  "window": "active",
  "bounding_box": { "x": 0, "y": 0, "width": 0, "height": 0 },
  "clickable": "likely",
  "obstructed": false,
  "disabled": false,
  "evidence": [
    { "source": "ocr", "value": "Download", "confidence": 0.91 },
    { "source": "visual_shape", "value": "button", "confidence": 0.88 },
    { "source": "ui_automation", "value": "Button", "confidence": 0.97 }
  ],
  "confidence": 0.96
}
```

Evidence must be combined. The ORB must not trust one detector when other sensors disagree.

High-confidence example:

```text
OCR says: Save
Visual model says: button
UI Automation says: Button control
Window context says: Save As dialog
Result: high-confidence Save button
```

Conflict example:

```text
OCR says: Delete
Visual model is uncertain
Window identity is unknown
Result: do not click; re-observe or ask Bryan
```

## Software LiDAR Boundaries

The sweep should detect:

- active monitor and full virtual desktop geometry
- active and overlapping windows
- visible controls and text
- target bounding boxes
- ORB-occupied blocked area
- modal dialogs and permission prompts
- safe hover and pointer paths
- low-confidence or contradictory regions

The sweep must remain bounded to the current task. It must not scan personal documents, emails, browser history, passwords, encrypted stores, cloud account contents, or financial data.

## Camera Perception

Camera perception is a separate physical-environment sensor. It does not replace desktop observation.

Camera use requires explicit permission before activation.

Camera path:

```text
user requests or approves camera use
-> select authorized camera
-> show visible camera-active indicator
-> capture only what the task requires
-> recognize objects and text
-> provide observations to TAMP
-> stop camera access when the task ends
```

Camera perception may combine:

- object recognition
- document OCR
- QR/barcode recognition
- document and label detection
- scene boundaries and object locations
- optional hand or gesture recognition only when separately approved
- confidence and source evidence

## Camera Permission Doctrine

- No automatic camera activation at startup.
- No background recording.
- No image or video saving unless explicitly approved.
- No face identification or recognition unless separately approved.
- No continuous monitoring merely because permission was granted once.
- A visible indicator must remain present while the camera is active.
- Bryan must be able to stop camera access immediately.
- Permission may be task-scoped, session-scoped, or persistent only when Bryan deliberately selects that mode.
- `observe desktop` and `look through the camera` are separate commands with separate permissions.

## Unified Loop

```text
See
-> recognize
-> understand
-> plan
-> point
-> obtain approval when required
-> act
-> verify
-> adapt
```

This prevents the Desktop ORB from behaving like a brittle macro recorder. The ORB observes the current environment, builds a temporary scene, plans with TAMP, verifies, and replans when the scene changes.
