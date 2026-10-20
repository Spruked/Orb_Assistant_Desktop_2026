
"""
CALISKG State Machine Integration — Changes to cali_skg.py

These are the exact modifications needed inside your existing cali_skg.py.
Everything else (LLM, voice engine, audio runtime, TTS) stays untouched.

AUTHOR: CALI v3.5+ State Machine Refactor
"""

# ============================================================================
# CHANGE 1: Add import at top of cali_skg.py
# ============================================================================

# ADD this import near the top of cali_skg.py, after existing imports:
from orb_state_machine import CALIStateMachine, CommandPhase


# ============================================================================
# CHANGE 2: In CALISKG.__init__(), replace self.orb_state initialization
# ============================================================================

# REMOVE this block (the old flat dict):
#     self.orb_state = {
#         "listening_enabled": False,
#         "voice_enabled": True,
#         "motion_enabled": True,
#         "cognition_enabled": True,
#         "system_alive": True,
#         ...
#     }

# REPLACE with:
        # State machine replaces flat orb_state dict
        # CALISKG owns the truth. All modules read/write through here.
        self.state_machine = CALIStateMachine(checkout_path=PROJECT_ROOT)

        # Seed initial desired states (same defaults as old orb_state)
        self.state_machine.set_desired_state("listening", {"enabled": False}, source="CALISKG.init")
        self.state_machine.set_desired_state("voice", {"enabled": True}, source="CALISKG.init")
        self.state_machine.set_desired_state("motion", {"enabled": True}, source="CALISKG.init")
        self.state_machine.set_desired_state("cognition", {"enabled": True}, source="CALISKG.init")
        self.state_machine.set_desired_state("system", {"orb_alive": True}, source="CALISKG.init")

        # Backward compatibility: orb_state now proxies to state_machine
        # Existing code that reads self.orb_state["listening_enabled"] still works
        self.orb_state = _OrbStateProxy(self.state_machine)


# ============================================================================
# CHANGE 3: Add _OrbStateProxy class inside cali_skg.py (or nearby)
# ============================================================================

class _OrbStateProxy:
    """
    Backward-compatibility proxy so existing code that reads/writes
    self.orb_state["key"] continues to work while we migrate.

    Writes go to desired layer. Reads come from effective layer.
    """
    def __init__(self, state_machine: CALIStateMachine):
        self._sm = state_machine

        # Mapping from old flat keys to new (domain, key) pairs
        self._key_map = {
            "listening_enabled": ("listening", "enabled"),
            "voice_enabled":     ("voice", "enabled"),
            "motion_enabled":    ("motion", "enabled"),
            "cognition_enabled": ("cognition", "enabled"),
            "system_alive":      ("system", "orb_alive"),
            "mic_ready":         ("listening", "mic_available"),
            "tts_ready":         ("voice", "tts_ready"),
            "llm_ready":         ("cognition", "llm_ready"),
            "presence_ready":    ("presence", "presence_ready"),
        }

    def __getitem__(self, key):
        if key in self._key_map:
            domain, state_key = self._key_map[key]
            eff = self._sm.get_effective_state(domain)
            return eff.get(state_key, False)
        # Fallback: try to read from any domain
        for domain in CALIStateMachine.DOMAINS:
            eff = self._sm.get_effective_state(domain)
            if key in eff:
                return eff[key]
        raise KeyError(key)

    def __setitem__(self, key, value):
        if key in self._key_map:
            domain, state_key = self._key_map[key]
            self._sm.set_desired_state(domain, {state_key: value}, source="CALISKG.orb_state_proxy")
        else:
            # Unknown key — store in system domain as desired
            self._sm.set_desired_state("system", {key: value}, source="CALISKG.orb_state_proxy")

    def __contains__(self, key):
        try:
            self.__getitem__(key)
            return True
        except KeyError:
            return False

    def get(self, key, default=None):
        try:
            return self.__getitem__(key)
        except KeyError:
            return default

    def update(self, other):
        for k, v in other.items():
            self.__setitem__(k, v)

    def to_dict(self):
        """Return the old-style flat dict for legacy callers."""
        return {
            "listening_enabled": self.__getitem__("listening_enabled"),
            "voice_enabled":     self.__getitem__("voice_enabled"),
            "motion_enabled":    self.__getitem__("motion_enabled"),
            "cognition_enabled": self.__getitem__("cognition_enabled"),
            "system_alive":      self.__getitem__("system_alive"),
            "mic_ready":         self.__getitem__("mic_ready"),
            "tts_ready":         self.__getitem__("tts_ready"),
            "llm_ready":         self.__getitem__("llm_ready"),
        }


# ============================================================================
# CHANGE 4: Replace sync_runtime_state() method in CALISKG
# ============================================================================

# REMOVE the old sync_runtime_state() that mutates self.orb_state directly.
# REPLACE with this version that writes to the state machine's RUNTIME layer:

    def sync_runtime_state(self, listening_enabled=None, auto_listen=None, 
                           cp3_io=None, mic_ready=None, tts_ready=None, 
                           llm_ready=None, presence_ready=None, **kwargs):
        """
        Sync runtime state from subsystem probes.

        WRITES to state machine RUNTIME layer (ground truth from subsystems).
        Does NOT mutate desired or effective directly — those are derived.

        Called by: audio probes, TTS health checks, LLM status polls.
        """
        runtime_report = {"checked_at": time.time()}

        if mic_ready is not None:
            runtime_report["mic_available"] = mic_ready
            if not mic_ready:
                runtime_report["mic_error"] = kwargs.get("mic_error", "mic_not_ready")

        if cp3_io is not None:
            runtime_report["cp3_ready"] = cp3_io
            if not cp3_io:
                runtime_report["cp3_error"] = kwargs.get("cp3_error", "cp3_not_ready")

        if tts_ready is not None:
            runtime_report["tts_ready"] = tts_ready
            if not tts_ready:
                runtime_report["tts_error"] = kwargs.get("tts_error", "tts_not_ready")

        if llm_ready is not None:
            runtime_report["llm_ready"] = llm_ready
            if not llm_ready:
                runtime_report["llm_error"] = kwargs.get("llm_error", "llm_not_ready")

        if presence_ready is not None:
            runtime_report["presence_ready"] = presence_ready
            if not presence_ready:
                runtime_report["presence_error"] = kwargs.get("presence_error", "presence_not_ready")

        # Write to state machine RUNTIME layer
        self.state_machine.update_runtime_state("listening", runtime_report, source="CALISKG.sync")
        self.state_machine.update_runtime_state("voice", runtime_report, source="CALISKG.sync")
        self.state_machine.update_runtime_state("cognition", runtime_report, source="CALISKG.sync")
        self.state_machine.update_runtime_state("presence", runtime_report, source="CALISKG.sync")

        # Legacy: return the old-style dict for callers expecting it
        return self.orb_state.to_dict()


# ============================================================================
# CHANGE 5: Replace get_status() method in CALISKG
# ============================================================================

# REMOVE the old get_status() that probes subsystems and mutates state.
# REPLACE with this PURE READ version:

    def get_status(self) -> dict:
        """
        PURE READ. Returns current effective state from the state machine.

        NEVER probes subsystems. NEVER mutates state.
        Only reads what sync_runtime_state() and health probes have already written.

        Backward-compatible shape for existing callers (bridge, DockStation, etc.)
        """
        return self.state_machine.get_status()

    def get_full_status(self) -> dict:
        """
        PURE READ. Returns complete four-layer state dump for debugging.
        """
        return self.state_machine.get_full_state()

    def get_diagnostic(self, domain: str = "listening") -> dict:
        """Deep diagnostic for a specific domain."""
        return self.state_machine.diagnose_listening() if domain == "listening" else {
            "desired": self.state_machine.get_desired_state(domain),
            "runtime": self.state_machine.get_runtime_state(domain),
            "effective": self.state_machine.get_effective_state(domain),
            "activity": self.state_machine.get_activity_state(domain),
        }


# ============================================================================
# CHANGE 6: Replace set_orb_state() / set_speech_recognition() in CALISKG
# ============================================================================

# Old set_speech_recognition() probably did:
#     self.orb_state["listening_enabled"] = enabled
#     self.speech_enabled = enabled
#
# REPLACE with:

    def set_speech_recognition(self, enabled: bool, source: str = "CALISKG") -> dict:
        """
        Set desired listening state. Effective state derived automatically.

        Returns effective state so caller knows if it actually worked.
        """
        self.state_machine.set_desired_state("listening", {"enabled": enabled}, source=source)

        # Legacy attribute for code that checks self.speech_enabled
        self.speech_enabled = enabled

        # Return effective state (tells caller if it's actually listening)
        return self.state_machine.get_effective_state("listening")


# ============================================================================
# CHANGE 7: Wire CALIFloatingOrb to use CALISKG's state_machine
# ============================================================================

# In floating_assistant_orb.py, in CALIFloatingOrb.__init__() or _attach_modules(),
# REMOVE the line that creates a separate state_machine on orb.
# Instead, use the one owned by CALISKG:

# OLD (what I had before — wrong):
#     if not hasattr(orb, "state_machine"):
#         orb.state_machine = CALIStateMachine(checkout_path=PROJECT_ROOT)

# NEW (correct — CALISKG owns the truth):
#     orb.state_machine = orb.skg.state_machine  # CALISKG owns it

# Then OrbLifecycle, OrbCommandRouter, OrbBehaviorRuntime all use:
#     self.state_machine = orb.state_machine  # which is orb.skg.state_machine


# ============================================================================
# CHANGE 8: Update floating_assistant_orb_main.py _attach_modules()
# ============================================================================

# The corrected _attach_modules() that properly wires through CALISKG:

def _attach_modules(orb: CALIFloatingOrb) -> None:
    """
    Attach modules with CALISKG as the state authority.

    Wire order:
      1. CALISKG already owns state_machine (created in its __init__)
      2. OrbLifecycle uses CALISKG's state_machine for health probes
      3. OrbCommandRouter routes commands through CALISKG's state_machine
      4. OrbBehaviorRuntime checks effective state from CALISKG
    """

    # CALISKG owns the state machine. Just verify it's there.
    if not hasattr(orb, "skg") or not hasattr(orb.skg, "state_machine"):
        raise RuntimeError("CALIFloatingOrb must have CALISKG with state_machine initialized")

    # STEP 1: Attach lifecycle (health probes write to RUNTIME)
    orb.lifecycle = OrbLifecycle(orb)

    # STEP 2: Attach behavior runtime (checks EFFECTIVE before acting)
    orb.behavior_runtime = OrbBehaviorRuntime(orb)

    # STEP 3: Patch orb methods
    orb.start = orb.lifecycle.start
    orb.stop = orb.lifecycle.stop
    orb.get_status = orb.lifecycle.get_status          # PURE READ
    orb.refresh_runtime_health = orb.lifecycle.refresh_runtime_health

    orb.process_cursor_movement = orb.behavior_runtime.process_cursor_movement
    orb.cognitively_emerge = orb.behavior_runtime.cognitively_emerge
    orb.idle_cognition = orb.behavior_runtime.idle_cognition

    orb._detect_whistle_summon = orb.behavior_runtime.detect_whistle_summon
    orb._is_cali_summon_request = orb.behavior_runtime.is_cali_summon_request
    orb._process_verbal_command = orb.behavior_runtime.process_verbal_command

    # NEW: Full speech pipeline
    orb.process_speech_pipeline = orb.behavior_runtime.process_speech_pipeline

    # NEW: Diagnostic methods
    orb.get_full_status = orb.lifecycle.get_full_status
    orb.get_diagnostic = orb.lifecycle.get_diagnostic


# ============================================================================
# CHANGE 9: Update OrbLifecycle to use orb.skg.state_machine
# ============================================================================

# In OrbLifecycle.__init__():

    def __init__(self, orb: "CALIFloatingOrb"):
        self.orb = orb

        # CALISKG owns the state machine. Use it.
        self.state_machine = orb.skg.state_machine

        # ... rest stays the same


# ============================================================================
# CHANGE 10: Update OrbCommandRouter to use orb.skg.state_machine
# ============================================================================

# In OrbCommandRouter.__init__():

    def __init__(self, orb: "CALIFloatingOrb"):
        self.orb = orb
        self.state_machine = orb.skg.state_machine

        # ... rest stays the same


# ============================================================================
# CHANGE 11: Update OrbBehaviorRuntime to use orb.skg.state_machine
# ============================================================================

# In OrbBehaviorRuntime.__init__():

    def __init__(self, orb: "CALIFloatingOrb"):
        self.orb = orb
        self.state_machine = orb.skg.state_machine

        # ... rest stays the same


# ============================================================================
# SUMMARY: What stays untouched in cali_skg.py
# ============================================================================

# These are NOT changed:
#   - LLM client initialization and query methods
#   - Voice engine manager (voice_engine_manager.py integration)
#   - Audio runtime integration (audio_runtime.py)
#   - TTS client integration (tts_client.py)
#   - All SKG reasoning logic, prompt templates, context windows
#   - All memory/consolidation logic
#   - All encryption/security code
#   - All import statements except the one orb_state_machine import
#   - All method signatures except sync_runtime_state, get_status, set_speech_recognition
#   - All the complex CALI v3.5 orchestration logic

# The only changes are:
#   1. Add one import
#   2. Replace orb_state init with state_machine init + proxy
#   3. Add _OrbStateProxy class
#   4. Replace sync_runtime_state() to write to RUNTIME layer
#   5. Replace get_status() to be pure read from EFFECTIVE layer
#   6. Replace set_speech_recognition() to write to DESIRED layer
#   7. Wire CALIFloatingOrb to use orb.skg.state_machine
