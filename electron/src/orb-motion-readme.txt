This branch loads orb-presence-bootstrap.js before orb-renderer.js.

The bootstrap converts passive cursor position updates into autonomous workspace loci:
- active display selection remains in Electron main.js
- real cursor input remains context for avoidance only
- the renderer receives an independent workspace reference
- explicit task choreography is reserved for deliberate task targets

The original renderer and DockStation remain intact.
