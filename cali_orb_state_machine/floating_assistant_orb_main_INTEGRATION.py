
"""
floating_assistant_orb_main.py — UPDATED integration example

This shows the exact changes needed to wire the four new modules
into the existing floating_assistant_orb_main.py.

CHANGES from original:
  1. Import CALIStateMachine (creates state_machine on orb)
  2. OrbLifecycle now creates state_machine if missing
  3. OrbBehaviorRuntime patches orb methods AFTER lifecycle
  4. All get_status() calls are now pure reads
  5. Command routing goes through OrbCommandRouter with lifecycle

The original _main() function body stays EXACTLY the same.
Only _attach_modules() changes.
"""

from __future__ import annotations

import os
import sys
import threading
import urllib.request
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT.parent))

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from floating_assistant_orb import CALIFloatingOrb
from orb_lifecycle import OrbLifecycle
from orb_behavior_runtime import OrbBehaviorRuntime
from orb_command_router import OrbCommandRouter

# NEW: Import the state machine core
from orb_state_machine import CALIStateMachine


def _attach_modules(orb: CALIFloatingOrb) -> None:
    """
    UPDATED: Attach the three new domain modules as attributes on orb.

    Wire order (CRITICAL — must happen in this order):
      1. Create CALIStateMachine on orb (truth authority)
      2. Attach OrbLifecycle (health probes write to runtime layer)
      3. Attach OrbBehaviorRuntime (behaviors check effective layer)
      4. Attach OrbCommandRouter (commands route through lifecycle)
    """

    # STEP 1: Create state machine (truth authority)
    # OrbLifecycle will use this, BehaviorRuntime will use this
    if not hasattr(orb, "state_machine"):
        orb.state_machine = CALIStateMachine(checkout_path=PROJECT_ROOT)

    # STEP 2: Attach lifecycle module
    # Health probes write to RUNTIME layer
    # get_status() reads from EFFECTIVE layer (pure read)
    orb.lifecycle = OrbLifecycle(orb)

    # STEP 3: Attach behavior runtime
    # All behaviors check effective state before executing
    orb.behavior_runtime = OrbBehaviorRuntime(orb)

    # STEP 4: Patch orb methods to route through new modules
    # so existing call sites (speech loop, etc.) still work unchanged.

    # Lifecycle methods
    orb.start = orb.lifecycle.start
    orb.stop = orb.lifecycle.stop
    orb.get_status = orb.lifecycle.get_status          # ← PURE READ
    orb.refresh_runtime_health = orb.lifecycle.refresh_runtime_health

    # Behavior methods
    orb.process_cursor_movement = orb.behavior_runtime.process_cursor_movement
    orb.cognitively_emerge = orb.behavior_runtime.cognitively_emerge
    orb.idle_cognition = orb.behavior_runtime.idle_cognition

    # Speech manager methods
    orb._detect_whistle_summon = orb.behavior_runtime.detect_whistle_summon
    orb._is_cali_summon_request = orb.behavior_runtime.is_cali_summon_request
    orb._process_verbal_command = orb.behavior_runtime.process_verbal_command

    # NEW: Full speech pipeline (speech_manager can call this directly)
    orb.process_speech_pipeline = orb.behavior_runtime.process_speech_pipeline

    # NEW: Diagnostic methods
    orb.get_full_status = orb.lifecycle.get_full_status
    orb.get_diagnostic = orb.lifecycle.get_diagnostic


def _main() -> None:
    """
    EXACTLY the same as original.
    The _attach_modules() changes above make everything work.
    """
    orb = CALIFloatingOrb(PROJECT_ROOT)
    _attach_modules(orb)

    # Start all background threads via OrbLifecycle
    orb.start()

    # Optional UCM status check (non-blocking; failures are logged, not fatal)
    if os.getenv("ORB_ENABLE_UCM_STATUS_CHECK", "0").strip().lower() in {"1", "true", "yes", "on"}:
        try:
            with urllib.request.urlopen("http://localhost:5050/orb/status", timeout=5) as resp:
                data = json.loads(resp.read().decode())
                status = data.get("status")
                print(f"UCM status: {status}", file=sys.stderr)
        except Exception as e:
            print(f"UCM status check failed: {e}", file=sys.stderr)

    # Kick off a background health refresh so the first get_status call
    # has real probe data instead of stale defaults.
    threading.Thread(
        target=orb.refresh_runtime_health, daemon=True, name="orb-health-refresh"
    ).start()

    router = OrbCommandRouter(orb)
    router.emit_ready()   # ← Electron bridge unblocks here
    router.run()          # ← blocks until "shutdown" or EOF


if __name__ == "__main__":
    _main()
