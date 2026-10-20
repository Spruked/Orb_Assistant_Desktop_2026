"""
orb_command_router.py — IPC stdin loop and all msg_type dispatch branches.

Extracted from floating_assistant_orb.py _main():
  - The full for-line-in-sys.stdin loop
  - Every msg_type branch (query, research, speak, listen_once, ...)
  - _emit_with_compliance (defined ONCE — no more closure duplication)
  - request_id safety (never crashes the loop on a missing field)
  - Bridge readiness ack (immediate ack before processing begins)

Design rule: zero business logic here.
Every branch delegates immediately to an orb subsystem.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import urllib.request
import uuid
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from floating_assistant_orb import CALIFloatingOrb

from audio_runtime import AUDIO_IMPORT_STATUS
from orb_state_machine import CommandPhase
from orb_routing_meta import make_route_meta, primitive_meta


class OrbCommandRouter:
    """
    Reads sys.stdin line-by-line (JSON-Lines / JSON-RPC style).
    Dispatches each message by type to the appropriate orb method.

    Lifecycle:
      router = OrbCommandRouter(orb)
      router.emit_ready()   # send the "ready" handshake
      router.run()          # blocks until shutdown or EOF
    """

    def __init__(self, orb: "CALIFloatingOrb"):
        self.orb = orb
        self.state_machine = getattr(orb, "state_machine", None)

    # ── Ready handshake ───────────────────────────────────────────────────────

    def emit_ready(self) -> None:
        """
        Emit the ready payload immediately after orb.start().
        Electron bridge waits for this before sending any queries.
        """
        orb = self.orb
        orb._emit({
            "type":                 "ready",
            "orb_standard_version": "1.0.0",
            "orb_shell":            os.getenv("ORB_SHELL", "desktop"),
            "cp3_status": {
                "cp3_root_set":       bool(os.getenv("CP3_ROOT")),
                "audio_runtime":      orb.audio_runtime.audio_runtime_status,
                "speech_available":   orb.audio_runtime.audio_runtime_status.get("speech") != "unavailable",
                "tts_available":      orb.audio_runtime.audio_runtime_status.get("voice")  != "unavailable",
                "audio_import_status": AUDIO_IMPORT_STATUS,
            },
            "alignment_layer": "active",
            "primitive_cache": "active",
        })

    # ── Main loop ─────────────────────────────────────────────────────────────

    def run(self) -> None:
        """
        Block on sys.stdin.
        Each JSON line is parsed and dispatched.
        Malformed lines are silently skipped (Electron sends noise sometimes).
        Exceptions inside dispatch are caught per-message — never crash the loop.
        """
        for raw_line in sys.stdin:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                msg = json.loads(raw_line)
            except Exception:
                continue
            try:
                should_exit = self._dispatch_with_lifecycle(msg)
                if should_exit:
                    break
            except Exception as exc:
                import traceback
                request_id = msg.get("request_id") if isinstance(msg, dict) else None
                print(
                    f"[OrbCommandRouter] dispatch error (request_id={request_id}): "
                    f"{exc}\n{traceback.format_exc()}",
                    file=sys.stderr,
                )

    # Telemetry and bookkeeping, not commands: no lifecycle events. cursor_move arrives about twice a
    # second; as commands they flooded the bridge and pushed real commands out of the 100-entry history.
    _LIFECYCLE_EXEMPT = {"memory_record", "motion_report", "cursor_move"}

    def _dispatch_with_lifecycle(self, msg: Dict[str, Any]) -> bool:
        msg_type = msg.get("type", "unknown")
        if msg_type in self._LIFECYCLE_EXEMPT:
            return self._dispatch(msg)
        request_id = msg.get("request_id") or f"req_{uuid.uuid4().hex[:8]}"
        msg["request_id"] = request_id
        if self.state_machine:
            self.state_machine.start_command(request_id, msg_type, msg, source="bridge")
            self.orb._emit({
                "type": "command_accepted",
                "request_id": request_id,
                "command_type": msg_type,
            })
            self.state_machine.transition_command(request_id, CommandPhase.EXECUTING)
        try:
            should_exit = self._dispatch(msg)
        except Exception as exc:
            if self.state_machine:
                self.state_machine.transition_command(request_id, CommandPhase.FAILED, error=str(exc))
            self.orb._emit({
                "type": "command_failed",
                "request_id": request_id,
                "command_type": msg_type,
                "error": str(exc),
            })
            raise
        if self.state_machine:
            self.state_machine.transition_command(request_id, CommandPhase.COMPLETED, result={"should_exit": should_exit})
            self.orb._emit({
                "type": "command_completed",
                "request_id": request_id,
                "command_type": msg_type,
                "result": {"should_exit": should_exit},
            })
        return should_exit

    # ── Dispatcher ────────────────────────────────────────────────────────────

    def _dispatch(self, msg: Dict[str, Any]) -> bool:
        """
        Route a message to the correct handler.
        Returns True if the loop should exit (shutdown received).
        """
        msg_type   = msg.get("type")
        request_id = msg.get("request_id")  # may be None — that is fine
        orb        = self.orb

        # ── Shutdown ─────────────────────────────────────────
        if msg_type == "shutdown":
            orb.stop()
            orb._emit({"type": "shutdown_ack", "request_id": request_id})
            return True  # signal loop exit

        # ── Cursor ───────────────────────────────────────────
        elif msg_type == "cursor_move":
            orb.behavior_runtime.process_cursor_movement(
                int(msg.get("x", 0)), int(msg.get("y", 0))
            )

        # ── Status ───────────────────────────────────────────
        elif msg_type == "get_status":
            orb._emit({
                "type":       "status_response",
                "request_id": request_id,
                "data":       orb.lifecycle.get_status(),
            })

        elif msg_type == "get_full_status":
            data = self.state_machine.get_full_state() if self.state_machine else {}
            orb._emit({
                "type":       "full_status_response",
                "request_id": request_id,
                "data":       data,
            })

        elif msg_type == "diagnose":
            domain = msg.get("domain", "listening")
            if domain == "listening" and self.state_machine:
                data = self.state_machine.diagnose_listening()
            elif self.state_machine:
                data = {
                    "desired": self.state_machine.get_desired_state(domain),
                    "runtime": self.state_machine.get_runtime_state(domain),
                    "effective": self.state_machine.get_effective_state(domain),
                    "activity": self.state_machine.get_activity_state(domain),
                }
            else:
                data = {"error": "state_machine_unavailable"}
            orb._emit({
                "type":       "diagnose_response",
                "request_id": request_id,
                "data":       data,
            })

        elif msg_type == "set_motion":
            from orb_state_machine import MotionTarget
            target_name = msg.get("target", "idle")
            enabled = bool(msg.get("enabled", target_name != "idle"))
            try:
                target = MotionTarget(target_name)
                if self.state_machine:
                    self.state_machine.set_desired_state("motion", {"enabled": enabled}, source="OrbCommandRouter.set_motion")
                    motion = self.state_machine.set_motion_target(target, msg.get("position")) if enabled else self.state_machine.complete_motion("disabled_by_user")
                    effective = self.state_machine.get_effective_state("motion")
                else:
                    motion = {}
                    effective = {}
                orb._emit({
                    "type": "motion_status",
                    "request_id": request_id,
                    "data": {"enabled": enabled, **motion, "effective": effective},
                })
            except ValueError:
                orb._emit({
                    "type": "motion_status",
                    "request_id": request_id,
                    "data": {"enabled": False, "error": f"unknown_motion_target:{target_name}"},
                })

        # ── Service control ──────────────────────────────────
        elif msg_type == "service_control":
            result = orb.handle_service_control(
                msg.get("service_id") or msg.get("service"),
                msg.get("action") or "status",
            )
            orb._emit({"type": "service_result", "request_id": request_id, "data": result})

        # ── Listen once ──────────────────────────────────────
        elif msg_type == "listen_once":
            accepted = orb.listen_once()
            orb._emit({
                "type":       "listen_once_ack",
                "request_id": request_id,
                "data":       {"accepted": accepted},
            })

        # ── Set listening ────────────────────────────────────
        elif msg_type == "set_listening":
            enabled = bool(msg.get("enabled", False))
            if self.state_machine:
                self.state_machine.set_desired_state(
                    "listening",
                    {"enabled": enabled},
                    source="OrbCommandRouter.set_listening",
                )
            ok      = orb.set_speech_recognition(enabled)
            effective = self.state_machine.get_effective_state("listening") if self.state_machine else {}
            orb._emit({
                "type":       "listening_mode",
                "request_id": request_id,
                "data": {
                    "enabled": effective.get("can_listen", orb.speech_enabled if ok else False),
                    "want_listen": effective.get("want_listen", enabled),
                    "mic_available": effective.get("mic_available"),
                    "cp3_ready": effective.get("cp3_ready"),
                    "block_reason": effective.get("block_reason"),
                    "block_source": effective.get("block_source"),
                    "block_checked_at": effective.get("block_checked_at"),
                    "ok":      ok,
                    "mode":    "continuous",
                },
            })

        # ── Speak ────────────────────────────────────────────
        elif msg_type == "speak":
            text    = msg.get("text", "")
            emotion = msg.get("emotion", "thoughtful_warm")
            payload = orb.build_voice_payload(text, emotion)
            self._emit_with_compliance(
                "speak_result", request_id, payload,
                visitor_input=text,
                intent={"reason": "speak"},
                orb_profile="desktop_orb",
            )

        # ── Set ORB state ────────────────────────────────────
        elif msg_type == "set_orb_state":
            setting = msg.get("setting")
            value = msg.get("value")

            state = {
                "instance_id": orb.instance_id,
                "running": orb.running,
                "controller_status": "active" if orb.controller else "inactive",
                "listening_enabled": orb.speech_enabled,
                "auto_listen": orb.auto_listen,
            }

            # ACK immediately so Electron never waits on slow/hung state application.
            orb._emit({
                "type": "orb_state_result",
                "request_id": request_id,
                "data": {"accepted": True, "ok": True, "state": state},
            })

            def _apply_state():
                try:
                    orb.set_cali_orb_state(setting, value)
                except Exception as exc:
                    print(f"set_orb_state apply error: {exc}", file=sys.stderr)

            threading.Thread(
                target=_apply_state,
                daemon=True,
                name="orb-set-state-apply",
            ).start()

        elif msg_type == "motion_report":
            # Motion runtime telemetry from the renderer (via Electron main): ground truth for motion.
            if self.state_machine is not None and isinstance(msg.get("report"), dict):
                self.state_machine.report_physical_motion(msg["report"], source="renderer")

        elif msg_type == "memory_record":
            self._handle_memory_record(msg)

        elif msg_type == "memory_recall":
            orb._emit({
                "type": "memory_recall_result",
                "request_id": request_id,
                "data": orb.memory.recall(str(msg.get("query", "")), int(msg.get("limit", 5))),
            })

        elif msg_type == "memory_status":
            orb._emit({
                "type": "memory_status_result",
                "request_id": request_id,
                "data": orb.memory.status(deep=bool(msg.get("deep"))),
            })

        elif msg_type == "research":
            self._handle_research(msg, request_id)

        # ── Query (main, multi-path branch) ──────────────────
        elif msg_type == "query":
            self._handle_query(msg, request_id)

        return False  # continue loop

    # ── Research handler ──────────────────────────────────────────────────────

    def _handle_research(self, msg: Dict, request_id: Any) -> None:
        orb     = self.orb
        query   = msg.get("query") or msg.get("text", "")
        domains: List[str] = msg.get("domains") or []
        research      = orb.run_research_request(query, domains)
        voice_payload = orb.build_voice_payload(research.get("response_text", ""))
        orb.last_response_text = research.get("response_text", "") or research.get("voice_response", "")
        self._emit_with_compliance(
            "research_result", request_id,
            {**research, **self._voice_fields(voice_payload)},
            visitor_input=query,
            intent={"reason": "research"},
            lead_payload={"domains": domains},
        )

    # ── Query handler ─────────────────────────────────────────────────────────

    def _handle_memory_record(self, msg: Dict[str, Any]) -> None:
        """Record an Electron-side interaction or observation in the single memory."""
        memory = getattr(self.orb, "memory", None)
        if memory is None:
            return
        metadata = msg.get("metadata") or {}
        if msg.get("kind") == "interaction":
            memory.interaction(
                msg.get("user_text", ""), msg.get("orb_text", ""), msg.get("channel", "desktop_chat"),
                metadata, request_id=metadata.get("request_id"),
            )
        else:
            memory.observe(
                msg.get("observation_type", "observation"),
                {"content": msg.get("content"), "metadata": metadata},
                tags=["electron"],
            )

    def _handle_query(self, msg: Dict, request_id: Any) -> None:
        orb  = self.orb
        text = msg.get("text", "")

        # ── 1. Alignment filter ──────────────────────────────
        _align = orb.alignment_layer.filter(text, {"source": "ipc_query"})
        if not _align["allowed"]:
            self._emit_with_compliance(
                "query_result", request_id,
                {
                    "echo":              text,
                    "response_text":     _align["reason"],
                    "alignment_blocked": True,
                    "alignment_code":    _align["code"],
                },
                visitor_input=text,
                intent={"reason": "alignment_blocked"},
            )
            return
        text = _align["sanitized"]

        # ── 2. Primitive cache ───────────────────────────────
        _prim = orb.primitive_cache.resolve(text)
        if _prim:
            orb.last_response_text = _prim["response_text"]
            _pv = orb.build_voice_payload(_prim["response_text"], _prim["emotion"])
            self._emit_with_compliance(
                "query_result", request_id,
                {
                    "echo":          text,
                    "response_text": _prim["response_text"],
                    "audio_path":    _pv.get("audio_path"),
                    "voice_package": _pv.get("voice_package"),
                    "_route_meta":   primitive_meta(_prim["entry_id"]),
                },
                visitor_input=text,
                intent={"reason": "primitive"},
            )
            orb.orb_heartbeat.record_route("primitive")
            return

        # ── 3. Current info guard ────────────────────────────
        _ci = orb.detect_current_info_intent(text)
        if _ci["is_current_info"]:
            _ci_text = (
                "I don't have access to live data right now. "
                "I can't check the current weather, prices, or real-time feeds "
                "without a connected tool."
            )
            orb.last_response_text = _ci_text
            _civ = orb.build_voice_payload(_ci_text)
            self._emit_with_compliance(
                "query_result", request_id,
                {
                    "echo":          text,
                    "response_text": _ci_text,
                    "audio_path":    _civ.get("audio_path"),
                    "voice_package": _civ.get("voice_package"),
                    "_route_meta":   make_route_meta(
                        provider_selected="tool_router",
                        provider_used="unsupported_tool_response",
                        cognition_mode="deterministic",
                        intent="current_info",
                        fallback_reason="no_live_tool_connected",
                        bypassed_provider=True,
                        bypassed_governance=True,
                        route_class="tool",
                        extra={"current_info_signal": _ci["signal"]},
                    ),
                },
                visitor_input=text,
                intent={"reason": "current_info"},
            )
            orb.orb_heartbeat.record_route("current_info_unsupported")
            return

        # ── 4. Frame input ───────────────────────────────────
        input_frame  = orb.frame_text_with_acp(
            text, context={"source": "ipc_query", "stimulus_type": "text_query"}
        )
        framed_text  = input_frame.get("normalized_text") or input_frame.get("transcript") or text

        # ── 5. Priority handler chain ────────────────────────
        #    Each returns a dict with at least "response_text", or None.
        #    First hit wins and returns.
        priority_handlers = [
            ("research_vault", orb.handle_research_vault_command,
                lambda t: orb.handle_research_vault_command(t),
                {"source": "research_vault"}),
            ("skill",          None,
                lambda t: orb.handle_skill_request(t, input_frame),
                {"source": "skill"}),
            ("core_knowledge", None,
                orb.handle_core_knowledge_request,
                {}),
            ("recall",         None,
                lambda t: orb.handle_recall_request(t, input_frame),
                {}),
        ]

        for intent_reason, _, handler_fn, lead in priority_handlers:
            result = handler_fn(framed_text)
            if result:
                vp = orb.build_voice_payload(result["response_text"])
                orb.last_response_text = result["response_text"]
                self._emit_with_compliance(
                    "query_result", request_id,
                    {
                        "echo":          text,
                        "input_frame":   input_frame,
                        "intent":        {"is_" + intent_reason: True},
                        "response_text": result["response_text"],
                        **self._voice_fields(vp),
                        intent_reason:   result,
                    },
                    visitor_input=text,
                    intent={"reason": intent_reason},
                    lead_payload=lead,
                )
                return

        # ── 6. Note intent ───────────────────────────────────
        note_result = orb.handle_note_request(framed_text, input_frame, source="text")
        if note_result:
            self._emit_with_compliance(
                "query_result", request_id,
                {
                    "echo":          text,
                    "input_frame":   input_frame,
                    "intent":        {"is_note": True},
                    "response_text": note_result["response_text"],
                    "notes":         note_result,
                },
                visitor_input=text,
                intent={"reason": "note"},
            )
            return

        # ── 7. Research or CALI reasoning ────────────────────
        intent   = orb.detect_research_intent(framed_text, input_frame)
        stimulus = {
            "type":        "text_query",
            "content":     framed_text,
            "coordinates": [0, 0],
            "velocity":    0.0,
            "input_frame": input_frame,
            "intent":      intent,
        }
        cognitive_result = orb.behavior_runtime.cognitively_emerge(stimulus)
        research         = None
        cali_reasoning   = None

        if intent.get("is_research"):
            research      = orb.run_research_request(framed_text, intent.get("domains") or [])
            response_text = research.get("response_text") or research.get("voice_response")
        else:
            cali_reasoning = orb.reason_with_cali(
                framed_text,
                context={
                    "source":         "ipc_query",
                    "stimulus_type":  "text_query",
                    "input_frame":    input_frame,
                    "semantic":       input_frame.get("semantic"),
                    "implied_intent": input_frame.get("implied_intent"),
                },
            )
            response_text = (
                cali_reasoning.get("recommended_response")
                if cali_reasoning
                else f"Analyzed: {framed_text}"
            )

        inline_voice  = os.getenv("ORB_INLINE_QUERY_VOICE", "0").strip().lower() in {"1", "true", "yes", "on"}
        voice_payload = (
            orb.build_voice_payload(
                response_text,
                "analytical" if research
                else orb.behavior_runtime.emotion_from_reasoning(cali_reasoning),
            )
            if inline_voice else {}
        )
        orb.last_response_text = response_text or ""

        _route_class    = "normal" if not research else "tool"
        _cognition_mode = (
            "research"   if research else
            "governance" if (cali_reasoning and cali_reasoning.get("governance_activated")) else
            "deterministic"
        )
        orb.orb_heartbeat.record_route(_route_class)
        orb.orb_heartbeat.set_cognition_mode(_cognition_mode)

        self._emit_with_compliance(
            "query_result", request_id,
            {
                "echo":               text,
                "input_frame":        input_frame,
                "intent":             intent,
                "response_text":      response_text,
                **self._voice_fields(voice_payload),
                "research":           research,
                "research_synthesis": research.get("research_synthesis") if research else None,
                "sources":            research.get("sources")            if research else [],
                "substrate_record":   research.get("substrate_record")   if research else None,
                "cali_reasoning":     cali_reasoning,
                "advisory_verdict":   cali_reasoning.get("advisory_verdict") if cali_reasoning else None,
                "cognitive_result":   (
                    cognitive_result.pulse()
                    if hasattr(cognitive_result, "pulse")
                    else cognitive_result
                ),
                "state": {
                    "instance_id":       orb.instance_id,
                    "running":           orb.running,
                    "controller_status": "active" if orb.controller else "inactive",
                    "listening_enabled": orb.speech_enabled,
                    "auto_listen":       orb.auto_listen,
                },
                "_route_meta": make_route_meta(
                    provider_selected=orb.instance_id,
                    provider_used="cali_skg" if cali_reasoning else "research_orchestrator",
                    cognition_mode=_cognition_mode,
                    intent=intent.get("reason", "general_query"),
                    route_class=_route_class,
                ),
            },
            visitor_input=text,
            intent=intent,
            lead_payload={"route_class": _route_class},
        )

    # ── _emit_with_compliance — defined ONCE ─────────────────────────────────

    def _emit_with_compliance(
        self,
        payload_type:  str,
        request_id:    Any,
        data:          Dict[str, Any],
        visitor_input: str = "",
        intent:        Optional[Dict] = None,
        lead_payload:  Optional[Dict] = None,
        orb_profile:   str = "website_orb",
    ) -> None:
        """
        Build a compliance envelope, enrich `data`, then emit.
        Single authoritative definition — no closure duplication.
        """
        orb           = self.orb
        voice_payload = {
            "audio_path":  data.get("audio_path"),
            "audio_url":   data.get("audio_url"),
            "tts_provider": data.get("tts_provider"),
            "audio_error": data.get("audio_error"),
        }
        compliance = orb.build_compliance_envelope(
            visitor_input=visitor_input,
            intent=intent or {},
            lead_payload=lead_payload or {},
            response_text=data.get("response_text", ""),
            voice_payload=voice_payload,
            orb_profile=orb_profile,
        )
        enriched                    = dict(data)
        enriched["compliance"]      = compliance
        enriched["site_orb_status"] = getattr(orb, "site_orb_status", {})
        orb._emit({
            "type":       payload_type,
            "request_id": request_id,
            "data":       enriched,
        })

    # ── Voice field extractor ─────────────────────────────────────────────────

    @staticmethod
    def _voice_fields(voice_payload: Dict) -> Dict[str, Any]:
        """Return the standard audio/TTS fields from a voice payload."""
        return {
            "audio_path":        voice_payload.get("audio_path"),
            "voice_package":     voice_payload.get("voice_package"),
            "tts_provider":      voice_payload.get("tts_provider"),
            "tts_fallback_used": voice_payload.get("tts_fallback_used"),
            "qwen_tts_endpoint": voice_payload.get("qwen_tts_endpoint"),
            "cp3_invoked":       voice_payload.get("cp3_invoked"),
            "audio_played":      voice_payload.get("audio_played"),
            "audio_error":       voice_payload.get("audio_error"),
        }
