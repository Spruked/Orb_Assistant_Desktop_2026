# ORB Desktop Pointer Runtime

Desktop-owned pointer plotting lives here. This folder belongs to the desktop MCP server, not the website ORBs.

Pointer plotting is on-demand TAMP-style targeting, not sitemap navigation. A request can identify a visible object, text label, UI element, region, or cursor-relative target at runtime; the pointer runtime resolves it into a coordinate frame and safe action.

Runtime folders:

- `state/` stores the latest local pointer state.
- `captures/` stores local scan captures.
- `actions/` stores resolved pointer actions.
- `baseline_maps/` stores fallback reference maps for recovery orientation.

Core files:

- `pointerPlotTypes.ts` shared TypeScript types.
- `pointerRuntime.ts` preserves the plot normalizer and implements the doctrine order: confidence, resolve, recover, point, ping, ploop.
- `pointerResolution.ts` preserves local action resolution and adds semantic locator, content fingerprint, accessibility role, and Tesseract visual verification.
- `orbState.ts` owns independent presence, guidance, and handoff state tracks.
- `orbEscalation.ts` preserves operator overrides and adds explicit-only, issue-scoped human handoff.
- `pointer_plot_schema.py` Python schema validation.
- `scan_extraction.py` local scene extraction and PlotRecord generation.
- `promotion.py` requires repeated matching corrections before changing an authoritative locator.
- `ocr_visual_verification.py` maps Tesseract TSV regions to doctrine PlotRecords.

Contract:

- `R:\Orb_Assistant_Desktop\docs\TAMP_ON_DEMAND_POINTER_CONTRACT.md`
- `R:\Orb_Assistant_Desktop\docs\BASELINE_REFERENCE_MAPS_CONTRACT.md`
- `R:\Orb_Assistant_Desktop\docs\DESKTOP_SCENE_SWEEP_PERCEPTION_CONTRACT.md`

Schemas:

- `R:\Orb_Assistant_Desktop\mcp\orb_desktop_mcp\orb_pointer\baseline_map.schema.json`
- `R:\Orb_Assistant_Desktop\mcp\orb_desktop_mcp\orb_pointer\observation_snapshot.schema.json`

Allowed automatic actions:

- observe
- hover_context
- point_at
- explain
- dismiss

Escalated actions:

- select
- open
- operator_override

Desktop ORB may point at visible targets on demand. It must not click, open, select, or otherwise perform side-effect actions without operator review.

Baseline maps are recovery scaffolds only. The pointer runtime must observe the live environment, resolve the target, act through TAMP, and verify the result. If confidence drops, a baseline map can help reorient and rebuild the temporary scene, but it cannot become the action plan.

Desktop Scene Sweep is the canonical live perception pass. It combines screen capture, monitor/window geometry, UI Automation, browser DOM when available, targeted Tesseract OCR, visual object recognition, blocked regions, and safe pointer paths into a temporary `ObservationSnapshot`.

The supplied website doctrine remains as reference at `R:\Orb_Assistant_Desktop\pointer doctrine files`. The deployed Desktop Assistant implementation lives under `R:\Services\orb_desktop_mcp\orb_pointer`.
