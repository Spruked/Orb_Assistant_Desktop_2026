"""
orb_lifecycle.py — ORB startup, shutdown, thread management, HLSF, heartbeat, status.

Extracted from floating_assistant_orb.py:
  start(), stop(), _cognitive_loop(), _hlsf_emit_loop(), _heartbeat_loop(),
  _write_mesh_heartbeat(), _build_hlsf_snapshot(), _cognitive_semantic_tag(),
  get_status(), refresh_runtime_health()

Design rule: this module knows about threads and state loops.
It does NOT know about IPC, audio routing, or research.
All cross-cutting reads go through self.orb.*
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    # Avoid circular import at runtime; type hints only.
    from floating_assistant_orb import CALIFloatingOrb

from orb_runtime_status import (
    build_runtime_snapshot,
    build_substrate_status,
    build_legacy_acp_io,
)
from orb_state_machine import CALIStateMachine


class OrbLifecycle:
    """
    Owns:
      - start() / stop() — including thread creation and join
      - Background loops: cognitive, HLSF emit, heartbeat, mesh heartbeat
      - get_status() — assembles the full status dict from all subsystems
      - refresh_runtime_health() — non-blocking health probe for LLM + TTS

    Does NOT own: IPC routing, audio playback, research, compliance envelopes.
    """

    def __init__(self, orb: "CALIFloatingOrb"):
        self.orb = orb
        self.state_machine = getattr(orb, "state_machine", None)
        if self.state_machine is None:
            self.state_machine = CALIStateMachine(checkout_path=getattr(orb, "project_root", Path(__file__).parent.parent.parent.resolve()))
            orb.state_machine = self.state_machine
        self._cognitive_thread: Optional[threading.Thread] = None
        self._hlsf_emit_thread: Optional[threading.Thread] = None
        self._heartbeat_thread: Optional[threading.Thread] = None

    # ── Start ─────────────────────────────────────────────────────────────────

    def start(self) -> None:
        orb = self.orb
        orb.running = True
        self.state_machine.set_desired_state("system", {"orb_alive": True}, source="OrbLifecycle.start")
        self.state_machine.set_activity_state("system", {"state": "running", "started_at": time.time()})

        self._cognitive_thread = threading.Thread(
            target=self._cognitive_loop, daemon=True, name="orb-cognitive"
        )
        self._cognitive_thread.start()

        self._hlsf_emit_thread = threading.Thread(
            target=self._hlsf_emit_loop, daemon=True, name="orb-hlsf"
        )
        self._hlsf_emit_thread.start()

        # Write initial mesh heartbeat synchronously so it exists before the loop.
        self._write_mesh_heartbeat()

        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop, daemon=True, name="orb-heartbeat"
        )
        self._heartbeat_thread.start()

        # Heartbeat self-report
        orb.orb_heartbeat.set_provider_status("active" if orb.controller else "inactive")
        orb.orb_heartbeat.set_permissions(
            ["voice", "presence", "research"] if orb.speech_enabled else ["presence", "research"]
        )
        orb.orb_heartbeat.start()
        orb.orb_heartbeat.emit_now()

        if orb.auto_listen:
            orb.set_speech_recognition(True)

    # ── Stop ──────────────────────────────────────────────────────────────────

    def stop(self) -> None:
        orb = self.orb
        orb.running        = False
        orb.speech_enabled = False
        self.state_machine.set_desired_state("system", {"orb_alive": False}, source="OrbLifecycle.stop")
        self.state_machine.set_activity_state("system", {"state": "stopping", "stopped_at": time.time()})

        for thread in (
            self._cognitive_thread,
            self._hlsf_emit_thread,
            self._heartbeat_thread,
        ):
            if thread and thread.is_alive():
                thread.join(timeout=1)

        # Desktop presence graceful shutdown
        if getattr(orb, "desktop_presence", None):
            try:
                orb.desktop_presence.graceful_shutdown()
            except Exception:
                pass

        # Swarm extension shutdown
        if getattr(orb, "swarm_extension", None):
            try:
                orb.swarm_extension.shutdown()
            except Exception:
                pass

        if orb.cali:
            orb.cali.close()

        if orb.controller and hasattr(orb.controller, "shutdown"):
            try:
                orb.controller.shutdown()
            except Exception:
                pass
        if getattr(orb, "memory", None) is not None:
            try:
                orb.memory.close()
            except Exception:
                pass
        self.state_machine.set_activity_state("system", {"state": "stopped", "stopped_at": time.time()})

    # ── Background loops ──────────────────────────────────────────────────────

    def _cognitive_loop(self) -> None:
        """Minimal loop — keeps the thread alive for any future tick work."""
        while self.orb.running:
            time.sleep(0.1)

    def _hlsf_emit_loop(self) -> None:
        """Emit an HLSF snapshot every 2 seconds."""
        while self.orb.running:
            try:
                snap = self._build_hlsf_snapshot()
                self.orb._emit({"type": "hlsf_snapshot", "data": snap})
            except Exception as e:
                print(f"HLSF emit loop error: {e}", file=sys.stderr)
            time.sleep(2)

    def _heartbeat_loop(self) -> None:
        """Write mesh heartbeat every 60 seconds and update orb_heartbeat status."""
        while self.orb.running:
            self._write_mesh_heartbeat()
            self.orb.orb_heartbeat.set_provider_status(
                "active" if self.orb.controller else "inactive"
            )
            self.orb.orb_heartbeat.set_cognition_mode(
                "speech_active" if self.orb.speech_enabled else "deterministic"
            )
            memory = getattr(self.orb, "memory", None)
            if memory is not None:
                try:
                    memory.maintain()  # rate-limited inside OrbMemory
                except Exception as exc:
                    print(f"Memory maintenance error: {exc}", file=sys.stderr)
            time.sleep(60)

    # ── HLSF snapshot ─────────────────────────────────────────────────────────

    def _cognitive_semantic_tag(self) -> str:
        mode = ""
        pres = getattr(self.orb, "latest_presence_update", None)
        if pres:
            mode = str(pres.get("cognitive_mode", "")).upper()
        if "INTUITION" in mode:
            return "intuiting"
        if "HABIT" in mode:
            return "habituating"
        if "GUARD" in mode:
            return "guarding"
        if "DEDUCTIVE" in mode:
            return "reasoning"
        return "idle"

    def _build_hlsf_snapshot(self) -> Dict[str, Any]:
        """Snapshot of the live HLSF engine for the Dock mirror.

        ``live`` is True only when the numbers below were read from the running engine in
        this call. With no engine the thresholds are 0/0 (not the engine defaults), so the
        Dock cannot show configured values as if they were live readings.
        """
        self._hlsf_seq = getattr(self, "_hlsf_seq", 0) + 1
        snapshot: Dict[str, Any] = {
            "position":    [0.0, 0.0],
            "active_dims": [],
            "hysteresis":  {
                "trigger":       0,
                "release":       0,
                "active":        False,
                "density_ratio": 0.0,
            },
            "field_density": 0,
            "semantic_tag":  self._cognitive_semantic_tag(),
            "live":   False,
            "source": "unavailable",
            "reason": "no HLSF engine attached to the controller",
            "seq":    self._hlsf_seq,
            "ts":     time.time(),
        }

        orb = self.orb
        if not (orb.controller and hasattr(orb.controller, "engine")):
            return snapshot

        try:
            engine    = orb.controller.engine
            field_map = engine.field_map
            density   = len(field_map)
            snapshot["field_density"] = density

            trigger = engine.purge_trigger_threshold
            release = engine.purge_release_threshold
            snapshot["hysteresis"] = {
                "trigger":       trigger,
                "release":       release,
                "active":        bool(engine.edge_cutter_active),
                "density_ratio": round(density / trigger, 3) if trigger > 0 else 0.0,
            }

            if field_map:
                top_nodes = sorted(
                    field_map.values(),
                    key=lambda n: n.cognitive_load,
                    reverse=True,
                )[:3]
                snapshot["active_dims"] = [
                    {
                        "n":      n.n,
                        "k":      n.k,
                        "energy": round(min(n.cognitive_load / 10.0, 1.0), 3),
                        "x":      round(n.coordinates[0], 4) if len(n.coordinates) > 0 else 0.0,
                        "y":      round(n.coordinates[1], 4) if len(n.coordinates) > 1 else 0.0,
                    }
                    for n in top_nodes
                ]
                cx = sum(d["x"] * d["energy"] for d in snapshot["active_dims"])
                cy = sum(d["y"] * d["energy"] for d in snapshot["active_dims"])
                total_e = sum(d["energy"] for d in snapshot["active_dims"]) or 1.0
                snapshot["position"] = [
                    round(cx / total_e, 4),
                    round(cy / total_e, 4),
                ]
            snapshot["live"] = True
            snapshot["source"] = "hlsf_engine"
            snapshot["reason"] = None
        except Exception as e:
            snapshot["live"] = False
            snapshot["source"] = "error"
            snapshot["reason"] = f"{type(e).__name__}: {e}"
            print(f"HLSF snapshot build error: {e}", file=sys.stderr)

        return snapshot

    # ── Mesh heartbeat ────────────────────────────────────────────────────────

    def _write_mesh_heartbeat(self) -> None:
        mesh_root = os.getenv("ORB_SHARED_MESH_ROOT", "").strip()
        if not mesh_root:
            return
        orb = self.orb
        try:
            snapshots_dir = (
                Path(mesh_root) / "exports" / orb.instance_id / "state_snapshots"
            )
            snapshots_dir.mkdir(parents=True, exist_ok=True)
            snap      = self._build_hlsf_snapshot()
            heartbeat = {
                "instance_id":       orb.instance_id,
                "ts":                time.time(),
                "running":           orb.running,
                "controller_status": "active" if orb.controller else "inactive",
                "listening_enabled": orb.speech_enabled,
                "hlsf":              snap,
            }
            (snapshots_dir / "heartbeat.json").write_text(
                json.dumps(heartbeat, indent=2), encoding="utf-8"
            )
        except Exception as e:
            print(f"Mesh heartbeat write failed: {e}", file=sys.stderr)

    # ── Health refresh (non-blocking, called from background thread) ──────────

    def refresh_runtime_health(self) -> None:
        """
        Probe local LLM and Qwen TTS health.
        Always called from a daemon thread — never blocks the IPC loop.
        """
        orb = self.orb
        try:
            orb.last_local_llm_health = orb.llm_client.health_check()
        except Exception as exc:
            orb.last_local_llm_health = {
                "ready":    False,
                "endpoint": orb.llm_client.get_endpoint(),
                "model":    orb.llm_client.get_model(),
                "error":    str(exc),
            }
        llm_ready = bool(orb.last_local_llm_health.get("ready") or orb.last_local_llm_health.get("connected"))
        self.state_machine.update_runtime_state(
            "cognition",
            {
                "llm_ready": llm_ready,
                "llm_error": None if llm_ready else orb.last_local_llm_health.get("error") or "llm_not_ready",
            },
            source="OrbLifecycle.refresh_runtime_health",
        )
        try:
            from tts_client import _probe_qwen_tts_health
            orb.last_qwen_tts_health = _probe_qwen_tts_health()
        except Exception as exc:
            orb.last_qwen_tts_health = {
                "ready":  False,
                "endpoint": orb.last_qwen_tts_health.get("endpoint", ""),
                "error":  str(exc),
            }
        tts_ready = bool(orb.last_qwen_tts_health.get("ready"))
        self.state_machine.update_runtime_state(
            "voice",
            {
                "tts_ready": tts_ready,
                "tts_error": None if tts_ready else orb.last_qwen_tts_health.get("error") or "tts_not_ready",
            },
            source="OrbLifecycle.refresh_runtime_health",
        )

    # ── get_status ────────────────────────────────────────────────────────────

    def get_status(self) -> Dict[str, Any]:
        """
        Assemble the full status dict.
        Reads from every subsystem but never calls blocking I/O
        (health probes happen in background via refresh_runtime_health).
        """
        orb     = self.orb
        now     = datetime.now().isoformat()
        cp3_path = getattr(orb, "_cp3_path", None)

        # ── decisions log ────────────────────────────────────
        decisions_path = orb.project_root / "CALI_System" / "memory" / "decisions.jsonl"
        last_decision  = None
        if decisions_path.exists():
            try:
                lines = [
                    l.strip()
                    for l in decisions_path.read_text(encoding="utf-8").splitlines()
                    if l.strip()
                ]
                if lines:
                    last_decision = json.loads(lines[-1])
            except Exception:
                pass

        # ── cp3_io ────────────────────────────────────────────
        cp3_io = dict(orb.audio_runtime.audio_runtime_status)
        cp3_path_obj = getattr(orb, "CP3_PATH", Path("__cp3_removed__"))
        cp3_io.setdefault("cp3_root",           str(cp3_path_obj))
        cp3_io.setdefault("cp3_root_exists",    cp3_path_obj.exists())
        cp3_io.setdefault("voice_runtime_ready",  False)
        cp3_io.setdefault("speech_runtime_ready", False)
        cp3_io.setdefault("text_framing_available", False)
        cp3_io.setdefault("state",              "UNKNOWN")
        cp3_io.setdefault("ready",              False)
        cp3_io.setdefault("last_error",         "")
        cp3_io.setdefault("last_updated",       now)

        from audio_runtime import AUDIO_IMPORT_STATUS, AUDIO_IMPORT_ERROR
        cp3_io["adapter_import_status"]    = AUDIO_IMPORT_STATUS
        cp3_io["adapter_import_error"]     = AUDIO_IMPORT_ERROR
        cp3_io["audio_runtime_status"]     = dict(orb.audio_runtime.audio_runtime_status)
        cp3_io["speech_adapter_available"] = orb.audio_runtime.audio_runtime_status.get("speech") != "unavailable"
        cp3_io["speech_runtime_ready"]     = orb.audio_runtime.get_mic() is not None
        cp3_io["voice_adapter_available"]  = orb.audio_runtime.audio_runtime_status.get("voice") != "unavailable"
        cp3_io["voice_runtime_ready"]      = orb.audio_runtime.get_voice() is not None
        cp3_io["text_framing_available"]   = True
        cp3_io["audio_input_source"]       = "orb_microphone"
        cp3_io["text_input_source"]        = "ipc_query"
        cp3_io["listening_enabled"]        = orb.speech_enabled

        # ── local_llm ─────────────────────────────────────────
        local_llm = dict(orb.last_local_llm_health)
        local_llm.setdefault("endpoint",   orb.llm_client.get_endpoint())
        local_llm.setdefault("model",      orb.llm_client.get_model())
        local_llm.setdefault("route",
            orb.cali.orb_state.get("llm_route")
            if orb.cali else os.getenv("ORB_LLM_ROUTE", "local")
        )
        local_llm["governance_wrapper"]      = False
        local_llm.setdefault("ready",        False)
        local_llm.setdefault("state",        "UNKNOWN")
        local_llm.setdefault("last_error",   "")
        local_llm.setdefault("last_updated", now)
        local_llm["ollama_keep_alive"]       = os.getenv(
            "CALI_OLLAMA_KEEP_ALIVE", os.getenv("OLLAMA_KEEP_ALIVE", "15m")
        )
        local_llm["requested_gpu_layers"]    = orb.llm_client.get_gpu_options().get("num_gpu")
        local_llm["last_runtime"]            = dict(orb.llm_client.last_llm_runtime)

        # ── qwen_tts ──────────────────────────────────────────
        from tts_client import _active_qwen_tts_endpoint
        qwen_tts = dict(orb.last_qwen_tts_health)
        qwen_tts.setdefault("endpoint",          _active_qwen_tts_endpoint())
        qwen_tts.setdefault("realtime_endpoint",  os.getenv("ORB_REALTIME_TTS_BASE_URL"))
        qwen_tts.setdefault("provider",
            os.getenv("ORB_REALTIME_TTS_ENGINE", os.getenv("ORB_TTS_PROVIDER", "cosyvoice-stream"))
        )
        qwen_tts.setdefault("ready",        False)
        qwen_tts.setdefault("state",        "UNKNOWN")
        qwen_tts.setdefault("last_error",   "")
        qwen_tts.setdefault("last_updated", now)

        mic_ready = bool(
            cp3_io.get("speech_runtime_ready")
            or cp3_io.get("speech_adapter_available")
            or cp3_io.get("ears_connected")
        )
        cp3_ready = bool(
            cp3_io.get("ready")
            or cp3_io.get("voice_runtime_ready")
            or cp3_io.get("speech_runtime_ready")
            or cp3_io.get("ears_connected")
        )
        self.state_machine.set_desired_state(
            "listening",
            {"enabled": bool(orb.speech_enabled)},
            source="OrbLifecycle.get_status",
        )
        self.state_machine.update_runtime_state(
            "listening",
            {
                "mic_available": mic_ready,
                "cp3_ready": cp3_ready,
                "mic_error": None if mic_ready else cp3_io.get("last_error") or "mic_unavailable",
                "cp3_error": None if cp3_ready else cp3_io.get("last_error") or "cp3_not_ready",
            },
            source="OrbLifecycle.get_status",
        )
        self.state_machine.update_runtime_state(
            "voice",
            {
                "tts_ready": bool(qwen_tts.get("ready")),
                "tts_error": None if qwen_tts.get("ready") else qwen_tts.get("error") or qwen_tts.get("last_error") or "tts_not_ready",
            },
            source="OrbLifecycle.get_status",
        )
        self.state_machine.update_runtime_state(
            "cognition",
            {
                "llm_ready": bool(local_llm.get("ready") or local_llm.get("connected")),
                "llm_error": None if (local_llm.get("ready") or local_llm.get("connected")) else local_llm.get("error") or local_llm.get("last_error") or "llm_not_ready",
            },
            source="OrbLifecycle.get_status",
        )

        # ── research manager state ────────────────────────────
        rm = getattr(orb, "research_manager", None)

        # ── skill state ───────────────────────────────────────
        skill_registry   = getattr(orb, "skill_registry",   None)
        skill_loader     = getattr(orb, "skill_loader",     None)

        # ── service manifest (non-probing read) ───────────────
        service_manifest = orb.orb_services.load_service_manifest()

        status: Dict[str, Any] = {
            "instance_id":       orb.instance_id,
            "running":           orb.running,
            "controller_status": "active" if orb.controller else "inactive",
            "listening_enabled": orb.speech_enabled,
            "auto_listen":       orb.auto_listen,
            "project_root":      str(orb.project_root),
            "system_root":       str(orb.system_root),
            "shared_mesh_root":  orb.shared_mesh_root,
            "memory":            orb.memory.status() if getattr(orb, "memory", None) is not None else {"available": False},
            "runtimes":          self.state_machine.get_runtime_summary(),
            "notes": {
                "base_path":              str(orb.cali_notes.base_path),
                "active_topic":           rm.current_note_topic       if rm else None,
                "active_session":         str(rm.current_note_session) if rm and rm.current_note_session else None,
                "taking_notes":           rm.note_taking_enabled       if rm else False,
                "pending_notepad_summary": bool(rm.pending_notepad_summary) if rm else False,
                "last_notepad_path":      rm.last_notepad_path         if rm else None,
            },
            "core_knowledge": {
                "base_path": str(orb.core_knowledge.base_path) if orb.core_knowledge else None,
                "available": bool(orb.core_knowledge),
            },
            "skills": {
                "available":     bool(skill_registry),
                "catalog_count": len(skill_registry.catalog) if skill_registry else 0,
                "active":        sorted(skill_loader.get_active().keys()) if skill_loader else [],
                "last_decision": last_decision,
            },
            "research_vault": {
                "active_path": str(orb.research_vault.active_path) if orb.research_vault else None,
                "index_path":  str(orb.research_vault.index_path)  if orb.research_vault else None,
                "available":   bool(orb.research_vault),
            },
            "substrate":  build_substrate_status(orb),
            "cp3_io":     cp3_io,
            "local_llm":  local_llm,
            "qwen_tts":   qwen_tts,
            "services": {
                "domains":       [s.get("domain") for s in service_manifest],
                "items": [
                    {
                        **svc,
                        "service_status": (
                            orb.service_status_cache.get(str(svc.get("service_id") or svc.get("id")))
                            or orb.orb_services._service_status(svc, probe_network=False)
                        ),
                    }
                    for svc in service_manifest
                ],
                "manifest_path": (
                    str(orb.core_knowledge.base_path / "spruked" / "services.json")
                    if orb.core_knowledge else None
                ),
                "mode": "local_manifest_required",
            },
            "awareness_permissions": {
                "desktop_presence_enabled": os.getenv("ORB_ENABLE_DESKTOP_PRESENCE", "").strip().lower() in {"1", "true", "yes", "on"},
                "browser_awareness_enabled": os.getenv("ORB_ENABLE_BROWSER_AWARENESS", "1").strip().lower() in {"1", "true", "yes", "on"},
            },
            "site_orb_status": getattr(orb, "site_orb_status", {}),
        }

        status["acp_io"] = build_legacy_acp_io(cp3_io)
        state_machine_status = self.state_machine.get_status()
        status["state_machine"] = state_machine_status
        status["state_machine_full"] = self.state_machine.get_full_state()
        status["listening_mode"] = state_machine_status.get("listening_mode", {})
        status["voice_status"] = state_machine_status.get("voice_status", {})
        status["motion_status"] = state_machine_status.get("motion_status", {})
        status["cognition_status"] = state_machine_status.get("cognition_status", {})
        status["system_status"] = state_machine_status.get("system_status", {})
        status["command_status"] = state_machine_status.get("command_status", {})

        if orb.cali:
            status["cali_status"] = orb.cali.get_status()

        desktop_presence = getattr(orb, "desktop_presence", None)
        status["desktop_presence"] = (
            desktop_presence.get_status() if desktop_presence else {"running": False}
        )
        presence_update = getattr(orb, "latest_presence_update", None)
        if presence_update:
            status["presence_update"] = presence_update

        runtime_snapshot = build_runtime_snapshot(
            orb,
            cali_status=status.get("cali_status") or {},
            presence_status=status.get("desktop_presence") or {},
            presence_update=status.get("presence_update") or {},
            local_llm=local_llm,
            qwen_tts=qwen_tts,
            cp3_io=cp3_io,
            audio_runtime=cp3_io,
            controller=orb.controller,
        )
        for k in ("active_llm", "llm_connected", "qwen_tts_ready", "voice_ready", "last_error", "last_updated"):
            runtime_snapshot.setdefault(k, None)
        status["runtime_snapshot"] = runtime_snapshot

        # EGF state
        if orb.controller and getattr(orb.controller, "gravity_bridge", None):
            try:
                status["egf_state"] = orb.controller.gravity_bridge.get_visual_state()
            except Exception as exc:
                status["egf_state"] = {"type": "egf_state", "ok": False, "mode": "fault", "error": str(exc)}

        # Swarm extension
        swarm = getattr(orb, "swarm_extension", None)
        status["swarm_extension"] = swarm.get_status() if swarm else {"running": False}

        return status
