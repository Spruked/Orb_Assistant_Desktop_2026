"""
floating_assistant_orb_main.py — Entry point for the refactored ORB.

Replaces the _main() function in floating_assistant_orb.py.
Wire order:
  1. Instantiate CALIFloatingOrb (unchanged __init__)
  2. Attach the three new modules as orb attributes
  3. orb.start()  → OrbLifecycle.start()
  4. Optional UCM status check
  5. OrbCommandRouter.emit_ready() → sends the Electron bridge handshake
  6. OrbCommandRouter.run()        → blocks on stdin until shutdown

Nothing else. No business logic here.
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


def _attach_modules(orb: CALIFloatingOrb) -> None:
    """
    Attach the three new domain modules as attributes on orb.
    This keeps floating_assistant_orb.py's __init__ unchanged
    while giving the new modules a clean reference to orb.
    """
    if getattr(orb, "cali", None) is not None and hasattr(orb.cali, "state_machine"):
        orb.state_machine = orb.cali.state_machine

    orb._original_start = getattr(orb, "start", None)
    orb._original_stop = getattr(orb, "stop", None)
    orb._original_get_status = getattr(orb, "get_status", None)
    orb._original_refresh_runtime_health = getattr(orb, "refresh_runtime_health", None)
    orb._original_process_cursor = getattr(orb, "process_cursor_movement", None)
    orb._original_cognitively_emerge = getattr(orb, "cognitively_emerge", None)
    orb._original_idle_cognition = getattr(orb, "idle_cognition", None)
    orb._original_detect_whistle = getattr(orb, "_detect_whistle_summon", None)
    orb._original_is_cali_summon = getattr(orb, "_is_cali_summon_request", None)
    orb._original_process_verbal = getattr(orb, "_process_verbal_command", None)

    orb.lifecycle        = OrbLifecycle(orb)
    orb.behavior_runtime = OrbBehaviorRuntime(orb)
    # Patch orb methods to route through new modules
    # so existing call sites (speech loop, etc.) still work unchanged.
    orb.start                   = orb.lifecycle.start
    orb.stop                    = orb.lifecycle.stop
    orb.get_status              = orb.lifecycle.get_status
    orb.refresh_runtime_health  = orb.lifecycle.refresh_runtime_health
    orb.process_cursor_movement = orb.behavior_runtime.process_cursor_movement
    orb.cognitively_emerge      = orb.behavior_runtime.cognitively_emerge
    orb.idle_cognition          = orb.behavior_runtime.idle_cognition
    # Speech manager still calls orb._detect_whistle_summon and
    # orb._is_cali_summon_request / orb._process_verbal_command —
    # patch those too so no changes needed in audio_runtime / speech code.
    orb._detect_whistle_summon   = orb.behavior_runtime.detect_whistle_summon
    orb._is_cali_summon_request  = orb.behavior_runtime.is_cali_summon_request
    orb._process_verbal_command  = orb.behavior_runtime.process_verbal_command


def _main() -> None:
    orb = CALIFloatingOrb(PROJECT_ROOT)
    _attach_modules(orb)

    # Start all background threads via OrbLifecycle
    orb.start()

    # Optional UCM status check (non-blocking; failures are logged, not fatal)
    if os.getenv("ORB_ENABLE_UCM_STATUS_CHECK", "0").strip().lower() in {"1", "true", "yes", "on"}:
        try:
            with urllib.request.urlopen("http://localhost:5050/orb/status", timeout=5) as resp:
                data   = json.loads(resp.read().decode())
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
