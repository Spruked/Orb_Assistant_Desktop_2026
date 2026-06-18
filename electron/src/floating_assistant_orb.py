#!/usr/bin/env python3
"""Electron bridge shim for CALI Orb â€” REFACTORED orchestrator only.

Exposes CALIFloatingOrb for PythonShell usage and supports a simple stdin/stdout
message loop so the Electron bridge can coordinate readiness and queries.

Moved to modules:
  - tts_client.py      -> Qwen TTS + Kokoro fallback
  - audio_runtime.py   -> native Kokoro/faster-whisper adapter loading
  - voice_payload.py   -> build voice payload response object
  - llm_client.py      -> Ollama/Qwen local LLM calls
  - orb_notes.py       -> CaliNotes
  - core_knowledge.py  -> CaliCoreKnowledge
  - orb_services.py    -> service manifest/status/start/stop/open
  - orb_runtime_status.py -> normalized status helpers
"""

import asyncio
import base64
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT.parent))

def _convert_cross_platform_path(value):
    raw = str(value or "").strip()
    if not raw:
        return ""
    if sys.platform == "win32" and raw.startswith("/mnt/") and len(raw) > 6:
        drive = raw[5]
        rest = raw[7:].replace("/", "\\")
        return f"{drive.upper()}:\\{rest}"
    if sys.platform != "win32" and len(raw) > 2 and raw[1] == ":":
        drive = raw[0].lower()
        rest = raw[2:].replace("\\", "/").lstrip("/")
        return f"/mnt/{drive}/{rest}"
    return raw

def _first_existing_path(candidates):
    for candidate in candidates:
        normalized = _convert_cross_platform_path(candidate)
        if normalized and Path(normalized).exists():
            return Path(normalized)
    normalized = _convert_cross_platform_path(next((c for c in candidates if c), ""))
    return Path(normalized) if normalized else Path()

def _ensure_runtime_path_env(name, candidates):
    current = _convert_cross_platform_path(os.getenv(name, ""))
    if current and Path(current).exists():
        if current != os.getenv(name):
            os.environ[name] = current
        return current
    resolved = _first_existing_path(candidates)
    if resolved:
        os.environ[name] = str(resolved)
        return str(resolved)
    return current

SF_ORB_PATH = PROJECT_ROOT / "SF-ORB"
CP3_PATH = PROJECT_ROOT / "__cp3_removed__"
ACP_PATH = CP3_PATH

_KOKORO_ASSET_ROOTS = [
    r"C:\dev\Desktop\PLATFORM\spruked.com\Orb_Assistant\modules\Adaptive_Cochlear_Processor_v1\kokoro_baseline\assets",
    "/mnt/c/dev/Desktop/PLATFORM/spruked.com/Orb_Assistant/modules/Adaptive_Cochlear_Processor_v1/kokoro_baseline/assets",
]
_ensure_runtime_path_env(
    "KOKORO_MODEL_PATH",
    [os.getenv("KOKORO_MODEL_PATH"), *[str(Path(root) / "kokoro-v1.0.onnx") for root in _KOKORO_ASSET_ROOTS]],
)
_ensure_runtime_path_env(
    "KOKORO_VOICES_PATH",
    [os.getenv("KOKORO_VOICES_PATH"), *[str(Path(root) / "voices-v1.0.bin") for root in _KOKORO_ASSET_ROOTS]],
)
_ensure_runtime_path_env(
    "KOKORO_AUDIO_DIR",
    [os.getenv("KOKORO_AUDIO_DIR"), str(PROJECT_ROOT / "CALI_System" / "voice_cache")],
)

def _setup_component_paths():
    paths_configured = []
    if SF_ORB_PATH.exists():
        sys.path.insert(0, str(SF_ORB_PATH))
        print(f"âœ“ SF-ORB path configured: {SF_ORB_PATH}", file=sys.stderr)
        paths_configured.append("sf-orb")
    else:
        print(f"âš  SF-ORB path not found: {SF_ORB_PATH}", file=sys.stderr)
    return paths_configured

COMPONENT_PATHS = _setup_component_paths()

from audio_runtime import (
    AudioRuntime, AUDIO_IMPORT_STATUS, AUDIO_IMPORT_ERROR,
    ensure_audio_adapters, get_adapter_state,
)
from tts_client import TTSClient, _probe_qwen_tts_health, _speak_with_kokoro_fallback
from voice_payload import build_voice_payload, check_voice_display_mismatch
from llm_client import LLMClient, _probe_local_llm_health
from orb_notes import CaliNotes
from core_knowledge import CaliCoreKnowledge
from orb_services import OrbServices
from orb_runtime_status import build_runtime_snapshot, build_substrate_status, build_legacy_acp_io

if os.getenv("ORB_DEBUG_TORCH", "0").strip().lower() in {"1", "true", "yes", "on"}:
    try:
        import torch
        print("âœ“ TORCH IS NOW AVAILABLE", file=sys.stderr)
        print(f"PyTorch version: {torch.__version__}", file=sys.stderr)
    except ImportError:
        print("Torch still missing - gravity field disabled", file=sys.stderr)

from orb_controller import SF_ORB_Controller
from cali_skg import CALISKG
from substrate.spruk_legacy_orb.core.persistent_memory import record_runtime_voice_observation
from cognitive_inference import AlignmentLayer
from primitive_cache import PrimitiveCache
from orb_heartbeat import OrbHeartbeat
from orb_routing_meta import primitive_meta, tool_meta, fallback_meta, make_route_meta

DESKTOP_PRESENCE_AVAILABLE = False
DesktopPresence = None
ENABLE_PRESENCE_DEFAULT = False
try:
    from caleon_presence.core.desktop_presence import DesktopPresence
    DESKTOP_PRESENCE_AVAILABLE = True
except Exception as presence_import_error:
    print(f"âš ï¸ Desktop presence integration unavailable: {presence_import_error}", file=sys.stderr)

SWARM_EXTENSION_AVAILABLE = False
CaliSwarmExtensionRuntime = None
ShortTermResearchCache = None
ResearchEventVault = None
CALI_SKILLS_AVAILABLE = False
SkillArbitrator = None
SkillLoader = None
SkillMemoryBridge = None
SkillRegistry = None
ENABLE_SWARM_EXTENSION_DEFAULT = False
try:
    from cali_swarm_extension.runtime_bridge import CaliSwarmExtensionRuntime
    from cali_swarm_extension.research.swarm_research_orchestrator import (
        ResearchEventVault, ShortTermResearchCache,
    )
    SWARM_EXTENSION_AVAILABLE = True
except Exception as swarm_import_error:
    print(f"âš ï¸ Swarm extension integration unavailable: {swarm_import_error}", file=sys.stderr)

try:
    from cali_skills.core.arbitrator import SkillArbitrator
    from cali_skills.core.loader import SkillLoader
    from cali_skills.core.memory_bridge import SkillMemoryBridge
    from cali_skills.core.registry import SkillRegistry
    CALI_SKILLS_AVAILABLE = True
except Exception as skill_import_error:
    print(f"âš ï¸ CALI skills unavailable: {skill_import_error}", file=sys.stderr)


class CALIFloatingOrb:
    """Main orchestrator â€” delegates to specialized modules. Public API preserved."""

    def __init__(self, project_root):
        self.project_root = Path(project_root).resolve()
        self.instance_id = os.getenv("ORB_INSTANCE_ID", "wsl").strip() or "wsl"
        self.system_root = Path(os.getenv("ORB_SYSTEM_ROOT", str(self.project_root))).expanduser().resolve()
        self.shared_mesh_root = os.getenv("ORB_SHARED_MESH_ROOT")
        self.controller = None
        self.running = False
        self.last_cursor_pos = (0, 0)
        self.last_time = time.time()
        self.latest_presence_update = None
        self.auto_listen = os.getenv("ORB_AUTO_LISTEN", "0").strip().lower() in {"1", "true", "yes", "on"}
        self.speech_enabled = False
        self.speech_thread = None
        self.listen_once_thread = None
        self.speech_lock = threading.Lock()
        self._emit_lock = threading.Lock()
        self._latency_mask_lock = threading.Lock()
        self._latency_mask_playing_until = 0.0
        self._last_whistle_summon_at = 0.0
        self.cali = None
        self.desktop_presence = None
        self.swarm_extension = None

        self.audio_runtime = AudioRuntime(self.project_root, self.instance_id)
        self.tts_client = TTSClient(self.project_root, self.instance_id)
        self.llm_client = LLMClient()
        self.orb_services = OrbServices()
        self.last_local_llm_health = {"ready": False, "endpoint": self._active_local_endpoint(), "model": self._active_local_model(), "error": "not_checked_yet"}
        self.last_qwen_tts_health = {"ready": False, "endpoint": self._active_qwen_tts_endpoint(), "error": "not_checked_yet"}

        self.short_term_research_cache = (
            ShortTermResearchCache(self.project_root / "CALI_System" / "memory" / "short_term_cache.db")
            if ShortTermResearchCache else None
        )
        self.cali_notes = CaliNotes(self.project_root / "CALI_System" / "notes")
        self.core_knowledge = CaliCoreKnowledge(self.project_root / "CALI_System" / "core_knowledge")
        self.orb_services.core_knowledge = self.core_knowledge
        self.research_vault = (
            ResearchEventVault(self.project_root / "CALI_System" / "memory" / "research_vault")
            if ResearchEventVault else None
        )
        self.alignment_layer = AlignmentLayer()
        self.primitive_cache = PrimitiveCache()
        self.orb_heartbeat = OrbHeartbeat(
            orb_id=self.instance_id,
            orb_shell=os.getenv("ORB_SHELL", "desktop"),
            emit_fn=self._emit,
        )
        self.current_note_topic = None
        self.current_note_session = None
        self.note_taking_enabled = False
        self.last_response_text = ""
        self.latency_mask_phrase = os.getenv("ORB_LATENCY_MASK_PHRASE", "Just one moment.").strip() or "Just one moment."
        self.pending_notepad_summary = None
        self.last_notepad_path = None
        self.service_status_cache = {}
        self.skill_registry = None
        self.skill_loader = None
        self.skill_arbitrator = None
        self.skill_memory = None
        self._init_skill_library()
        self._ensure_decision_log()
        self.site_orb_status = {
            "spruked.com": self._default_site_orb_status(),
            "truemarkmint.com": self._default_site_orb_status(),
            "shilohridgekatahdins.com": self._default_site_orb_status(),
            "shilohridgekatahdins.com/butch": self._default_site_orb_status(),
        }

        try:
            self.cali = CALISKG(self.system_root)
            print("âœ“ CALI SKG v3 online", file=sys.stderr)
        except Exception as e:
            print(f"âš ï¸ CALI SKG init failed: {e}", file=sys.stderr)

        try:
            self.controller = SF_ORB_Controller(cali=self.cali)
        except Exception as exc:
            print(f"âš ï¸ Controller init failed: {exc}", file=sys.stderr)
            self.controller = SF_ORB_Controller()

        self.llm_client.cali = self.cali
        self._init_desktop_presence()
        self._init_swarm_extension()

        if self.auto_listen or os.getenv("ORB_PRELOAD_AUDIO_RUNTIME", "0").strip().lower() in {"1", "true", "yes", "on"}:
            self.audio_runtime.init_audio_runtime(preload=True)
        else:
            self.audio_runtime.audio_runtime_status["adapters"] = "idle"
            self.audio_runtime.audio_runtime_status["voice"] = "idle"
            self.audio_runtime.audio_runtime_status["speech"] = "idle"

    # --- Audio / TTS delegation ---

    def _start_audio_runtime_init(self):
        self.audio_runtime.init_audio_runtime(preload=True)

    def _ensure_audio_adapters(self):
        return ensure_audio_adapters()

    def _ensure_voice_runtime(self):
        return self.audio_runtime.ensure_voice_runtime()

    def _ensure_mic_runtime(self):
        return self.audio_runtime.ensure_mic_runtime()

    def _init_audio_runtime(self):
        self.audio_runtime.init_audio_runtime(preload=False)

    def _active_qwen_tts_endpoint(self):
        from tts_client import _active_qwen_tts_endpoint as fn
        return fn()

    def _probe_qwen_tts_health(self):
        return _probe_qwen_tts_health()

    def _resolve_audio_path_from_qwen(self, payload):
        from tts_client import _resolve_audio_path_from_qwen as fn
        return fn(payload, self.project_root, self.instance_id)

    def _speak_with_qwen_tts(self, text):
        from tts_client import _speak_with_qwen_tts as fn
        return fn(text, self.instance_id, self._active_local_model(), str(self.project_root))

    def _speak_with_kokoro_fallback(self, text):
        self.audio_runtime.ensure_voice_runtime()
        return self.tts_client._speak_with_kokoro_fallback(
            text,
            voice_instance=self.audio_runtime.get_voice(),
            instance_id=self.instance_id,
            active_local_model=self._active_local_model(),
        )

    def speak(self, text):
        """Public speak: universal real-time TTS primary."""
        self.tts_client.set_voice_instance(self.audio_runtime.get_voice())
        result = self.tts_client.speak(text)
        self.audio_runtime.audio_runtime_status["tts_provider"] = result.get("tts_provider", os.getenv("ORB_REALTIME_TTS_ENGINE", "cosyvoice-stream"))
        self.audio_runtime.audio_runtime_status["tts_fallback_used"] = result.get("tts_fallback_used", False)
        self.audio_runtime.audio_runtime_status["tts_primary_error"] = result.get("tts_primary_error", "")
        self.audio_runtime.audio_runtime_status["realtime_tts_endpoint"] = result.get("realtime_tts_endpoint") or os.getenv("ORB_REALTIME_TTS_BASE_URL")
        self.audio_runtime.audio_runtime_status["qwen_tts_endpoint"] = result.get("qwen_tts_endpoint")
        return result

    def prepare_voice(self, text, emotion="thoughtful_warm"):
        if not self.cali:
            return None
        try:
            return self.cali.speak(text, emotion)
        except Exception as e:
            print(f"CALI voice packaging error: {e}", file=sys.stderr)
            return None

    def build_voice_payload(self, text, emotion="thoughtful_warm"):
        """Public API preserved."""
        voice_package = self.prepare_voice(text, emotion)
        speak_result = None
        audio_path = None
        if not self.cali or self.cali.orb_state.get("voice_active", True):
            speak_result = self.speak(text)
            if isinstance(speak_result, dict):
                audio_path = speak_result.get("audio_path")
        return build_voice_payload(text, speak_result, voice_package)

    # --- LLM delegation ---

    def _active_local_endpoint(self):
        return self.llm_client.get_endpoint()

    def _active_local_model(self):
        return self.llm_client.get_model()

    def _ollama_gpu_options(self):
        return self.llm_client.get_gpu_options()

    def _probe_local_llm_health(self):
        return self.llm_client.health_check()

    def _query_local_llm(self, text):
        result = self.llm_client.query(text)
        if result and result.get("llm_runtime"):
            self.llm_client.last_llm_runtime = result["llm_runtime"]
        return result

    # --- Voice emission â€” preserved public API ---

    def emit_spoken_text(self, text, emotion="thoughtful_warm", request_id=None):
        check_voice_display_mismatch(self.last_response_text, text, emit_fn=self._emit)
        payload = self.build_voice_payload(text, emotion)
        self._emit({"type": "speak_result", "request_id": request_id, "data": payload})
        return payload

    def _voice_budget_text(self, text, min_chars=120, max_chars=220):
        raw = " ".join(str(text or "").split())
        if len(raw) <= max_chars:
            return raw
        sentences = re.split(r"(?<=[.!?])\s+", raw)
        selected = []
        total = 0
        for sentence in sentences:
            if not sentence:
                continue
            next_total = total + len(sentence) + (1 if selected else 0)
            if selected and next_total > max_chars:
                break
            selected.append(sentence)
            total = next_total
            if total >= min_chars:
                break
        short = " ".join(selected).strip()
        if short:
            return short[:max_chars].rstrip()
        return raw[:max_chars].rsplit(" ", 1)[0].rstrip() or raw[:max_chars].rstrip()

    def _latency_mask_audio_path(self):
        return self.project_root / "CALI_System" / "voice_cache" / "latency_mask_just_one_moment.wav"

    def _ensure_latency_mask_audio(self):
        audio_path = self._latency_mask_audio_path()
        if audio_path.exists() and audio_path.stat().st_size > 44:
            return str(audio_path)
        result = _speak_with_kokoro_fallback(
            self.latency_mask_phrase,
            voice_instance=self.audio_runtime.get_voice(),
            instance_id=self.instance_id,
            active_local_model=self._active_local_model(),
        )
        generated = result.get("audio_path") if isinstance(result, dict) else None
        if generated and Path(generated).exists():
            audio_path.parent.mkdir(parents=True, exist_ok=True)
            if Path(generated) != audio_path:
                audio_path.write_bytes(Path(generated).read_bytes())
            return str(audio_path)
        return None

    def emit_latency_mask_speech(self):
        if os.getenv("ORB_LATENCY_MASK_SPEECH", "1").strip().lower() not in {"1", "true", "yes", "on"}:
            return None
        now = time.time()
        with self._latency_mask_lock:
            if now < self._latency_mask_playing_until:
                return None
            self._latency_mask_playing_until = now + 3.0
        audio_path = self._ensure_latency_mask_audio()
        if not audio_path:
            return None
        self._emit({
            "type": "speech_pulse",
            "data": {"latency_mask": True, "response_text": self.latency_mask_phrase},
            "response_text": self.latency_mask_phrase,
            "spoken_text": self.latency_mask_phrase,
            "audio_path": audio_path,
            "audio_url": None,
            "tts_provider": "kokoro",
            "tts_fallback_used": True,
            "latency_mask": True,
            "audio_error": "",
        })
        return audio_path

    def _default_site_orb_status(self):
        return {
            "connected": True,
            "listeners_on": bool(self.speech_enabled),
            "llm_ok": bool(self.last_local_llm_health.get("connected") or self.last_local_llm_health.get("ready")),
            "tts_ok": bool(self.last_qwen_tts_health.get("ready")),
            "crm_ok": False,
            "mail_ok": False,
            "mesh_ok": False,
            "voice_ok": False,
            "e2e_ok": False,
            "last_interaction_at": None,
            "last_interaction_id": None,
            "last_error": "",
        }

    def _infer_site_id(self, visitor_input, intent=None):
        text = str(visitor_input or "").lower()
        reason = str((intent or {}).get("reason") or "").lower()
        domain_hints = [str(x).lower() for x in ((intent or {}).get("domains") or [])]
        if "butch" in text or "ranch" in text or "livestock" in text:
            return "shilohridgekatahdins.com/butch"
        if "truemark" in text or "mint" in text:
            return "truemarkmint.com"
        if "shiloh" in text or "katahdin" in text or "farm" in text or "ranch" in reason:
            return "shilohridgekatahdins.com"
        if any("finance" in d or "commerce" in d for d in domain_hints):
            return "truemarkmint.com"
        if any("geospatial" in d or "weather" in d for d in domain_hints):
            return "shilohridgekatahdins.com"
        return "spruked.com"

    def _probe_local_http(self, url, timeout=2.0):
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                code = int(getattr(response, "status", 200))
                return {"ok": 200 <= code < 500, "status_code": code, "error": ""}
        except Exception as exc:
            return {"ok": False, "status_code": 0, "error": str(exc)}

    def _write_compliance_mesh_artifact(self, envelope):
        mesh_root = str(os.getenv("ORB_SHARED_MESH_ROOT", "")).strip()
        if not mesh_root:
            return {"ok": False, "path": "", "error": "ORB_SHARED_MESH_ROOT not set"}
        try:
            base = Path(mesh_root) / "exports" / self.instance_id / "compliance" / str(envelope.get("site_id") or "unknown").replace("/", "_")
            base.mkdir(parents=True, exist_ok=True)
            artifact_path = base / f"{envelope['interaction_id']}.json"
            artifact_path.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
            return {"ok": True, "path": str(artifact_path), "error": ""}
        except Exception as exc:
            return {"ok": False, "path": "", "error": str(exc)}

    def build_compliance_envelope(self, visitor_input, intent=None, lead_payload=None, response_text="", voice_payload=None, orb_profile="website_orb"):
        site_id = self._infer_site_id(visitor_input, intent or {})
        interaction_id = f"orb-{uuid.uuid4()}"
        now = datetime.now().isoformat()
        crm_probe = self._probe_local_http("http://127.0.0.1:21000/health")
        mail_probe = self._probe_local_http("http://127.0.0.1:19000/api/health")
        voice_payload = voice_payload or {}
        voice_ok = bool(voice_payload.get("audio_path") or voice_payload.get("audio_url") or str(voice_payload.get("tts_provider", "")).lower() == "qwen")
        envelope = {
            "interaction_id": interaction_id,
            "site_id": site_id,
            "orb_profile": orb_profile,
            "visitor_input": str(visitor_input or ""),
            "intent": intent or {},
            "lead_payload": lead_payload or {},
            "crm_result": {
                "ok": bool(crm_probe.get("ok")),
                "status_code": crm_probe.get("status_code", 0),
                "record_id": interaction_id,
                "error": crm_probe.get("error", ""),
            },
            "mail_handoff_result": {
                "ok": bool(mail_probe.get("ok")),
                "status_code": mail_probe.get("status_code", 0),
                "ticket_id": interaction_id,
                "error": mail_probe.get("error", ""),
            },
            "mesh_artifact_path": "",
            "voice_result": {
                "ok": voice_ok,
                "provider": voice_payload.get("tts_provider") or "unknown",
                "audio_path": voice_payload.get("audio_path"),
                "audio_url": voice_payload.get("audio_url"),
                "audio_error": voice_payload.get("audio_error", ""),
            },
            "runtime_status": {
                "listening_enabled": bool(self.speech_enabled),
                "auto_listen": bool(self.auto_listen),
                "llm_connected": bool(self.last_local_llm_health.get("connected") or self.last_local_llm_health.get("ready")),
                "qwen_tts_ready": bool(self.last_qwen_tts_health.get("ready")),
                "updated_at": now,
            },
        }
        mesh_write = self._write_compliance_mesh_artifact(envelope)
        envelope["mesh_artifact_path"] = mesh_write.get("path", "")
        mesh_ok = bool(mesh_write.get("ok"))
        crm_ok = bool(envelope["crm_result"]["ok"])
        mail_ok = bool(envelope["mail_handoff_result"]["ok"])
        e2e_ok = crm_ok and mail_ok and mesh_ok
        if e2e_ok:
            stage = "complete"
            stage_ok = True
            error_code = ""
            error_message = ""
        else:
            stage = "failed"
            stage_ok = False
            if not crm_ok:
                error_code = "crm_unavailable"
                error_message = envelope["crm_result"].get("error") or "CRM health unavailable"
            elif not mail_ok:
                error_code = "mail_unavailable"
                error_message = envelope["mail_handoff_result"].get("error") or "Mail handoff unavailable"
            else:
                error_code = "mesh_write_failed"
                error_message = mesh_write.get("error", "mesh artifact write failed")
        envelope["compliance_result"] = {
            "site_id": site_id,
            "compliance_stage": stage,
            "stage_ok": stage_ok,
            "error_code": error_code,
            "error_message": error_message,
            "artifact_refs": {
                "crm_record_id": envelope["crm_result"].get("record_id"),
                "mail_ticket_id": envelope["mail_handoff_result"].get("ticket_id"),
                "mesh_file_path": envelope.get("mesh_artifact_path", ""),
            },
        }
        status_row = self.site_orb_status.get(site_id, self._default_site_orb_status())
        status_row.update({
            "connected": True,
            "listeners_on": bool(self.speech_enabled),
            "llm_ok": bool(self.last_local_llm_health.get("connected") or self.last_local_llm_health.get("ready")),
            "tts_ok": bool(self.last_qwen_tts_health.get("ready")),
            "crm_ok": crm_ok,
            "mail_ok": mail_ok,
            "mesh_ok": mesh_ok,
            "voice_ok": voice_ok,
            "e2e_ok": e2e_ok,
            "last_interaction_at": now,
            "last_interaction_id": interaction_id,
            "last_error": error_message,
        })
        self.site_orb_status[site_id] = status_row
        return envelope

    # --- Notes â€” delegated to CaliNotes ---

    def extract_topic_from_query(self, query, input_frame=None):
        normalized = str(query or "").strip()
        semantic = (input_frame or {}).get("semantic") or {}
        implied = (input_frame or {}).get("implied_intent") or {}
        domain_hints = implied.get("domain_hints") or semantic.get("domain_terms") or []
        if domain_hints:
            hint = " ".join(str(item).strip() for item in domain_hints[:3] if str(item).strip())
            if hint:
                return hint
        lowered = normalized.lower()
        removals = (
            "cali", "please", "research", "look up", "lookup", "investigate",
            "find sources for", "find sources", "verify", "fact check",
            "compare sources for", "compare sources", "use the substrate", "substrate research",
        )
        topic = lowered
        for phrase in removals:
            topic = topic.replace(phrase, " ")
        topic = re.sub(r"[^a-z0-9\s_\-]+", " ", topic)
        topic = re.sub(r"\s+", " ", topic).strip()
        return topic[:80] or "general_notes"

    def ensure_note_session(self, topic):
        topic = topic or self.current_note_topic or "general_notes"
        if (
            self.current_note_session
            and self.current_note_topic
            and self.cali_notes.get_subject_path(self.current_note_topic)
            == self.cali_notes.get_subject_path(topic)
        ):
            return self.current_note_session
        self.current_note_topic = topic
        self.current_note_session = self.cali_notes.create_session(topic)
        return self.current_note_session

    def detect_note_intent(self, text, input_frame=None):
        normalized = str(text or "").strip()
        lowered = normalized.lower()
        semantic = (input_frame or {}).get("semantic") or {}
        semantic_intent = str(semantic.get("intent") or "").lower()
        triggers = (
            "/take note", "/save note", "take notes", "take note", "write that down",
            "save this", "save that", "don't save", "do not save", "discard notes",
            "discard that", "keep track",
        )
        return semantic_intent == "note" or any(trigger in lowered for trigger in triggers)

    def handle_note_request(self, text, input_frame=None, source="text"):
        if not self.detect_note_intent(text, input_frame):
            return None
        normalized = str(text or "").strip()
        lowered = normalized.lower()

        if any(phrase in lowered for phrase in ("don't save", "do not save", "discard notes", "discard that")):
            self.pending_notepad_summary = None
            payload = {
                "topic": self.current_note_topic,
                "session_path": str(self.current_note_session) if self.current_note_session else None,
                "note_text": "",
                "response_text": "Got it. I won't save that.",
            }
            self.emit_spoken_text(payload["response_text"])
            self._emit({"type": "note_result", "data": payload})
            return payload

        if any(phrase in lowered for phrase in ("save that", "save this", "/save note")) and self.pending_notepad_summary:
            saved = self.save_pending_summary()
            response_text = "Saved to the topic notes." if saved else "I do not have a pending summary ready to save."
            payload = {
                "topic": self.current_note_topic,
                "session_path": str(self.current_note_session) if self.current_note_session else None,
                "note_text": self.pending_notepad_summary.get("text") if self.pending_notepad_summary else "",
                "response_text": response_text,
            }
            self.emit_spoken_text(payload["response_text"])
            self._emit({"type": "note_result", "data": payload})
            return payload

        topic = self.current_note_topic or self.extract_topic_from_query(normalized, input_frame)
        session_path = self.ensure_note_session(topic)
        self.note_taking_enabled = True
        note_text = ""
        for trigger in ("/take note", "/save note", "write that down", "save this", "save that"):
            index = lowered.find(trigger)
            if index >= 0:
                note_text = normalized[index + len(trigger):].strip(" :-")
                break
        if not note_text:
            note_text = self.last_response_text or f"Note-taking started for {topic}."
        self.cali_notes.append(session_path, f"[{datetime.now().isoformat()}] {source}: {note_text}")
        payload = {
            "topic": topic,
            "session_path": str(session_path),
            "note_text": note_text,
            "response_text": "Got it. I'll keep track of what we find.",
        }
        self.emit_spoken_text(payload["response_text"])
        self._emit({"type": "note_result", "data": payload})
        return payload

    def build_research_notepad_summary(self, query, research, topic):
        synthesis = research.get("research_synthesis") or {}
        key_findings = synthesis.get("key_findings") or []
        sources = research.get("sources") or []
        summary = (
            research.get("response_text")
            or research.get("voice_response")
            or synthesis.get("summary")
            or " ".join(key_findings[:3])
            or "I do not have enough to confirm that yet."
        )
        lines = [
            f"CALI Research Summary: {topic}",
            f"Query: {query}",
            f"Generated: {datetime.now().isoformat()}",
            "",
            "Summary:",
            str(summary).strip(),
        ]
        if key_findings:
            lines.extend(["", "Key Points:"])
            lines.extend(f"- {point}" for point in key_findings[:8])
        if sources:
            lines.extend(["", "Sources:"])
            for source in sources[:10]:
                if not isinstance(source, dict):
                    continue
                title = source.get("title") or "Untitled"
                url = source.get("url") or source.get("source") or ""
                confidence = source.get("confidence")
                suffix = f" confidence={confidence}" if confidence is not None else ""
                lines.append(f"- {title}: {url}{suffix}")
        return "\n".join(lines).rstrip() + "\n"

    def open_notepad_summary(self, text):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w", encoding="utf-8") as handle:
            handle.write(text)
            temp_path = handle.name
        self.last_notepad_path = temp_path
        if sys.platform == "win32":
            subprocess.Popen(["notepad.exe", temp_path])
        else:
            print(f"Notepad summary prepared: {temp_path}", file=sys.stderr)
        return temp_path

    def save_pending_summary(self):
        if not self.pending_notepad_summary:
            return None
        topic = self.pending_notepad_summary.get("topic") or self.current_note_topic or "general_notes"
        text = self.pending_notepad_summary.get("text") or ""
        research = self.pending_notepad_summary.get("research") or {}
        session_path = self.ensure_note_session(topic)
        summary_path = self.cali_notes.write_summary(
            topic, text,
            key_points=(research.get("research_synthesis") or {}).get("key_findings") or [],
            sources=research.get("sources") or [],
        )
        for source in research.get("sources") or []:
            if isinstance(source, dict):
                source.setdefault("query", self.pending_notepad_summary.get("query"))
                self.cali_notes.append_source(topic, source)
        self.cali_notes.append(session_path, f"[{datetime.now().isoformat()}] saved_summary: {summary_path}")
        return summary_path

    def record_research_notes(self, query, research, input_frame=None):
        topic = self.extract_topic_from_query(query, input_frame)
        session_path = self.ensure_note_session(topic) if self.note_taking_enabled else None
        sources = research.get("sources") or []
        domains = research.get("domains") or []
        default_domain = domains[0] if isinstance(domains, list) and domains else None
        synthesis = research.get("research_synthesis") or {}
        key_findings = synthesis.get("key_findings") or []
        event_findings = [
            event.get("result_summary")
            for event in self.replay_research_events(topic=topic, min_confidence=0.7, limit=20)
            if event.get("result_summary")
        ]
        passive_points = list(key_findings or []) + event_findings
        if not self.note_taking_enabled:
            return {
                "topic": topic,
                "session_path": None,
                "passive_highlights": len(passive_points),
                "promoted_highlights": 0,
                "pending_only": True,
            }
        for source in sources:
            if isinstance(source, dict):
                source.setdefault("query", query)
                source.setdefault("domain", default_domain)
                self.cali_notes.append_source(topic, source)
        self.cali_notes.store_lightweight_summary(topic, query, passive_points, sources)
        summary = (
            research.get("response_text")
            or research.get("voice_response")
            or synthesis.get("summary")
            or " ".join(event_findings[:5])
            or ""
        )
        if summary:
            self.cali_notes.write_summary(topic, summary, key_points=passive_points, sources=sources)
        promoted = []
        if self.note_taking_enabled:
            promoted = self.cali_notes.promote_passive_highlights(topic, session_path)
        if self.note_taking_enabled and key_findings:
            self.cali_notes.append(session_path, "\nKey points:")
            for finding in key_findings[:5]:
                self.cali_notes.append(session_path, f"- {finding}")
        if self.note_taking_enabled and event_findings:
            self.cali_notes.append(session_path, "\nHigh-confidence event notes:")
            for finding in event_findings[:5]:
                self.cali_notes.append(session_path, f"- {finding}")
        return {
            "topic": topic,
            "session_path": str(session_path) if session_path else None,
            "passive_highlights": len(passive_points),
            "promoted_highlights": len(promoted),
        }

    # --- Core knowledge â€” delegated ---

    def handle_core_knowledge_request(self, text):
        result = self.core_knowledge.handle(text) if self.core_knowledge else None
        if not result:
            return None
        if result.get("action") == "operator_command":
            core = result.get("core") or {}
            launch = core.get("files", {}).get("launch.json")
            lowered = str(text or "").lower()
            if isinstance(launch, dict) and any(term in lowered for term in ("start ", "launch ")):
                command = str(launch.get("command") or "").strip()
                cwd = str(launch.get("cwd") or "").strip() or None
                if not command:
                    result["response_text"] = f"{result['subject']} is known, but its launch command is not configured yet."
                    return result
                subprocess.Popen(command, shell=True, cwd=cwd)
                result["response_text"] = f"Starting {result['subject']}."
                return result
            if any(term in lowered for term in ("open ", "status")):
                result["response_text"] = (
                    f"{result['subject']} is known. The local open/status command still needs a curated command entry."
                )
                return result
        return result

    # --- Services â€” delegated ---

    def load_service_manifest(self):
        return self.orb_services.load_service_manifest()

    def _find_service(self, service_id):
        return self.orb_services._find_service(service_id)

    def _probe_expected_ports(self, expected_ports):
        return self.orb_services._probe_expected_ports(expected_ports)

    def _service_status(self, service, probe_network=True):
        return self.orb_services._service_status(service, probe_network=probe_network)

    def handle_service_control(self, service_id, action):
        result = self.orb_services.handle_service_control(service_id, action)
        if result and "service_status" in result:
            svc = result.get("service")
            if svc:
                self.service_status_cache[str(svc.get("service_id") or svc.get("id"))] = result["service_status"]
        return result

    # --- Research / reasoning â€” preserved ---

    def emit_cali_state(self, phase, text, **extra):
        data = {"phase": phase, "text": text}
        data.update(extra)
        self._emit({"type": "cali:state", "data": data})
        self.record_research_event({"type": "cali:state", "data": data}, query=data.get("query"), topic=data.get("topic"))

    def record_research_event(self, event, query=None, topic=None):
        if not self.research_vault:
            return None
        try:
            return self.research_vault.append_event(event, query=query, topic=topic)
        except Exception as exc:
            print(f"Research vault event write failed: {exc}", file=sys.stderr)
            return None

    def replay_research_events(self, query=None, topic=None, min_confidence=None, limit=20):
        if not self.research_vault:
            return []
        return self.research_vault.replay(query=query, topic=topic, min_confidence=min_confidence, limit=limit)

    def handle_research_vault_command(self, text):
        normalized = str(text or "").strip().lower()
        if not self.research_vault:
            return None
        if "archive current research session" in normalized or "archive current research log" in normalized:
            archive_path = self.research_vault.archive_active()
            response_text = "Research log archived." if archive_path else "There was no active research log to archive."
            return {"response_text": response_text, "archive_path": str(archive_path) if archive_path else None}
        if "clear recent research log" in normalized or "purge active research log" in normalized:
            purge_path = self.research_vault.stage_active_for_purge()
            response_text = "Recent research log staged for purge." if purge_path else "There was no active research log to stage for purge."
            return {"response_text": response_text, "purge_path": str(purge_path) if purge_path else None}
        if "what did you find earlier" in normalized or "replay research" in normalized:
            topic = self.current_note_topic
            events = self.replay_research_events(topic=topic, limit=10)
            summaries = [event.get("result_summary") for event in events if event.get("result_summary")][:5]
            response_text = "Earlier findings: " + " ".join(summaries) if summaries else "I do not have enough recorded research to replay for this topic yet."
            return {"response_text": response_text, "events": events}
        return None

    def handle_recall_request(self, text, input_frame=None):
        normalized = str(text or "").strip()
        lowered = normalized.lower()
        triggers = (
            "what did we find about", "what did you find about", "what did we learn about",
            "continue research on", "continue notes on", "recall notes on",
        )
        if not any(trigger in lowered for trigger in triggers):
            return None
        topic = normalized
        for trigger in triggers:
            topic = re.sub(re.escape(trigger), " ", topic, flags=re.IGNORECASE)
        topic = topic.strip(" ?.:;-") or self.current_note_topic or "general_notes"
        summary = self.cali_notes.read_summary(topic)
        events = self.replay_research_events(topic=topic, limit=10)
        event_summaries = [event.get("result_summary") for event in events if event.get("result_summary")][:5]
        if summary:
            response_text = summary[:1200]
        elif event_summaries:
            response_text = "Recorded findings: " + " ".join(event_summaries)
        else:
            response_text = f"I don't have enough saved knowledge on {topic} yet."
        session_path = self.ensure_note_session(topic)
        self.current_note_topic = topic
        return {
            "topic": topic,
            "session_path": str(session_path),
            "summary": summary,
            "events": events,
            "response_text": response_text,
        }

    def reason_with_cali(self, text, context=None):
        if not self.cali:
            return None
        try:
            if self.cali.orb_state.get("llm_route") == "local":
                result = self._query_local_llm(text)
                if result:
                    return result
            return self.cali.reason(text, context=context or {})
        except Exception as e:
            print(f"CALI reasoning error: {e}", file=sys.stderr)
            return None

    def research_with_cali(self, query, domains=None):
        if not self.cali:
            return None
        domain_list = domains or []
        topic = self.extract_topic_from_query(query)
        note_meta = {
            "topic": topic,
            "session_path": str(self.current_note_session) if self.note_taking_enabled and self.current_note_session else None,
        }
        started_at = time.time()
        self.emit_cali_state("planning", "", query=query, domains=domain_list, topic=topic)
        self.emit_spoken_text(f"I'm glad I can help with your research on {topic}. If you want me to take notes, just say it or type it.")

        if self.short_term_research_cache:
            cached = self.short_term_research_cache.get(query, domain_list)
            if cached:
                if isinstance(cached, dict):
                    cached["_short_term_cache_hit"] = True
                    cached["_swarm_cache_hit"] = True
                    cached["notes"] = note_meta
                self.record_research_event({"type": "swarm:complete", "data": {"query": query, "topic": topic, "source": "short_term_cache", "cache_hit": True, "confidence": cached.get("confidence") if isinstance(cached, dict) else None, "result_summary": (cached.get("response_text") or cached.get("voice_response") or "") if isinstance(cached, dict) else "", "latency_ms": int((time.time() - started_at) * 1000)}}, query=query, topic=topic)
                if isinstance(cached, dict):
                    summary_text = self.build_research_notepad_summary(query, cached, topic)
                    self.pending_notepad_summary = {"topic": topic, "query": query, "text": summary_text, "research": cached, "created_at": datetime.now().isoformat()}
                    self.open_notepad_summary(summary_text)
                self.emit_cali_state("speaking", "", query=query, topic=topic)
                return cached

        if self.swarm_extension and hasattr(self.swarm_extension, "lookup_cached_research"):
            self.emit_cali_state("searching", "", query=query, topic=topic)
            cached = self.swarm_extension.lookup_cached_research(query, domain_list)
            if cached:
                if isinstance(cached, dict):
                    cached["_swarm_cache_hit"] = True
                    cached["notes"] = note_meta
                if self.short_term_research_cache:
                    self.short_term_research_cache.store(query, cached, domain_list, source="substrate")
                self.record_research_notes(query, cached)
                self.record_research_event({"type": "swarm:complete", "data": {"query": query, "topic": topic, "source": "substrate", "cache_hit": True, "confidence": cached.get("confidence") if isinstance(cached, dict) else None, "result_summary": (cached.get("response_text") or cached.get("voice_response") or "") if isinstance(cached, dict) else "", "latency_ms": int((time.time() - started_at) * 1000)}}, query=query, topic=topic)
                if isinstance(cached, dict):
                    summary_text = self.build_research_notepad_summary(query, cached, topic)
                    self.pending_notepad_summary = {"topic": topic, "query": query, "text": summary_text, "research": cached, "created_at": datetime.now().isoformat()}
                    self.open_notepad_summary(summary_text)
                self.emit_cali_state("speaking", "", query=query, topic=topic)
                return cached

        try:
            self.emit_cali_state("searching", "", query=query, topic=topic)
            research = asyncio.run(self.cali.research(query, domain_list))
            if isinstance(research, dict):
                research["_swarm_cache_hit"] = False
                research["notes"] = note_meta
            self.emit_cali_state("synthesizing", "", query=query, topic=topic)
            if research and self.short_term_research_cache:
                self.short_term_research_cache.store(query, research, domain_list, source="live_research")
            if research and self.swarm_extension and hasattr(self.swarm_extension, "store_research_result"):
                self.swarm_extension.store_research_result(query, domain_list, research)
            if research:
                summary_text = self.build_research_notepad_summary(query, research, topic)
                self.pending_notepad_summary = {"topic": topic, "query": query, "text": summary_text, "research": research, "created_at": datetime.now().isoformat()}
                self.open_notepad_summary(summary_text)
                research["notes"] = self.record_research_notes(query, research)
                synthesis = research.get("research_synthesis") or {}
                self.record_research_event({"type": "swarm:complete", "data": {"query": query, "topic": topic, "source": "live_research", "cache_hit": False, "confidence": research.get("confidence") or synthesis.get("confidence") or synthesis.get("confidence_aggregate"), "result_summary": research.get("response_text") or research.get("voice_response") or synthesis.get("summary") or " ".join((synthesis.get("key_findings") or [])[:3]), "latency_ms": int((time.time() - started_at) * 1000)}}, query=query, topic=topic)
            self.emit_cali_state("speaking", "", query=query, topic=topic)
            return research
        except Exception as e:
            print(f"CALI research error: {e}", file=sys.stderr)
            return None

    def detect_research_intent(self, text, input_frame=None):
        normalized = str(text or "").strip()
        lowered = normalized.lower()
        if not normalized:
            return {"is_research": False, "domains": [], "reason": "empty"}
        explicit_terms = (
            "research", "look up", "lookup", "find sources", "source check", "verify",
            "fact check", "investigate", "compare sources", "what are the sources",
            "current", "latest", "today", "recent", "web search", "search the web",
            "use the substrate", "substrate research",
        )
        question_terms = ("who is", "what is", "when did", "where is", "how many", "how much")
        domain_terms = {
            "finance": ("stock", "market", "price", "sec", "filing", "revenue", "earnings"),
            "academic": ("paper", "study", "journal", "citation", "scholar"),
            "biomedical": ("clinical", "medical", "health", "trial", "pubmed"),
            "weather": ("weather", "storm", "climate", "forecast"),
            "space": ("nasa", "space", "launch", "satellite", "astronomy"),
            "geospatial": ("map", "location", "geospatial", "earthquake", "transport"),
        }
        semantic = (input_frame or {}).get("semantic") or {}
        implied = (input_frame or {}).get("implied_intent") or {}
        action_terms = [str(term).lower() for term in semantic.get("action_terms", [])]
        domain_hints = [str(term).lower() for term in implied.get("domain_hints", [])]
        matched = [term for term in explicit_terms if term in lowered]
        if not matched:
            matched.extend([term for term in action_terms if term in {"research", "verify", "compare", "find"}])
        is_research = bool(matched)
        if not is_research and any(term in lowered for term in question_terms):
            is_research = any(term in lowered for term in ("latest", "current", "today", "recent", "source", "verify"))
        domains = []
        for domain, terms in domain_terms.items():
            if domain in domain_hints or any(term in lowered for term in terms):
                domains.append(domain)
        return {"is_research": is_research, "domains": domains, "reason": matched[0] if matched else ("current_question" if is_research else "general_query")}

    _CURRENT_INFO_SIGNALS = (
        "noaa", "weather now", "weather right now", "current weather", "live weather",
        "check noaa", "check the weather", "what is the weather", "real-time", "live price",
        "current price", "stock price now", "live score", "scores right now", "current news",
        "latest news now", "what time is it", "live data", "right now",
    )
    _CURRENT_INFO_LIVE_NOUNS = re.compile(r"\b(weather|temperature|price|news|score|rate|status|forecast)\b")

    def detect_current_info_intent(self, text):
        lowered = str(text or "").lower().strip()
        for signal in self._CURRENT_INFO_SIGNALS:
            if signal in lowered:
                return {"is_current_info": True, "signal": signal}
        if re.search(r"\bnow\b", lowered) and self._CURRENT_INFO_LIVE_NOUNS.search(lowered):
            return {"is_current_info": True, "signal": "live_data_pattern"}
        return {"is_current_info": False}

    def normalize_research_response(self, query, domains, research):
        payload = dict(research or {})
        synthesis = payload.get("research_synthesis")
        if not isinstance(synthesis, dict):
            synthesis = {}
            payload["research_synthesis"] = synthesis
        sources = payload.get("sources") or payload.get("references") or synthesis.get("sources") or []
        if not isinstance(sources, list):
            sources = [sources]
        payload.setdefault("query", query)
        payload.setdefault("domains", domains or [])
        payload["sources"] = sources
        payload["source_count"] = len(sources) or int(synthesis.get("sources_queried") or 0)
        payload["confidence"] = synthesis.get("confidence_aggregate", synthesis.get("confidence", 0.0))
        payload["response_text"] = payload.get("voice_response") or payload.get("summary") or "Research complete."
        payload["substrate_record"] = {"cache_hit": bool(payload.get("_swarm_cache_hit")), "query": query, "domains": domains or []}
        if payload.get("notes"):
            payload["notes"] = payload["notes"]
        return payload

    def run_research_request(self, query, domains=None):
        domain_list = domains or []
        research = self.research_with_cali(query, domain_list) or {"voice_response": "Research is unavailable right now.", "research_synthesis": {"error": "CALI research offline"}}
        return self.normalize_research_response(query, domain_list, research)

    def hear_with_cali(self, audio_signal):
        if not self.cali:
            return None
        try:
            return asyncio.run(self.cali.hear(audio_signal))
        except Exception as e:
            print(f"CALI hearing error: {e}", file=sys.stderr)
            return None

    def _detect_whistle_summon(self, audio_data, sample_rate):
        try:
            import numpy as np
        except Exception:
            return False

        try:
            cooldown = float(os.getenv("ORB_WHISTLE_SUMMON_COOLDOWN_SEC", "4.0"))
            now = time.time()
            if now - self._last_whistle_summon_at < cooldown:
                return False

            signal = np.asarray(audio_data, dtype=np.float32).flatten()
            if signal.size < max(1024, int(sample_rate * 0.25)):
                return False

            signal = signal - float(np.mean(signal))
            rms = float(np.sqrt(np.mean(signal * signal)))
            min_rms = float(os.getenv("ORB_WHISTLE_MIN_RMS", "0.018"))
            if rms < min_rms:
                return False

            max_samples = int(sample_rate * 1.6)
            if signal.size > max_samples:
                signal = signal[:max_samples]

            window = np.hanning(signal.size).astype(np.float32)
            spectrum = np.abs(np.fft.rfft(signal * window))
            freqs = np.fft.rfftfreq(signal.size, d=1.0 / float(sample_rate))
            if spectrum.size < 8:
                return False

            whistle_min = float(os.getenv("ORB_WHISTLE_MIN_HZ", "1150"))
            whistle_max = float(os.getenv("ORB_WHISTLE_MAX_HZ", "4200"))
            band_mask = (freqs >= whistle_min) & (freqs <= whistle_max)
            low_mask = (freqs >= 120) & (freqs < 950)
            if not np.any(band_mask):
                return False

            band = spectrum[band_mask]
            peak = float(np.max(band))
            band_sum = float(np.sum(band)) + 1e-9
            total_sum = float(np.sum(spectrum)) + 1e-9
            low_sum = float(np.sum(spectrum[low_mask])) + 1e-9
            peak_freq = float(freqs[band_mask][int(np.argmax(band))])
            tonal_ratio = peak / band_sum
            band_energy_ratio = band_sum / total_sum
            high_to_low_ratio = band_sum / low_sum

            if (
                tonal_ratio >= float(os.getenv("ORB_WHISTLE_TONAL_RATIO", "0.18"))
                and band_energy_ratio >= float(os.getenv("ORB_WHISTLE_BAND_RATIO", "0.34"))
                and high_to_low_ratio >= float(os.getenv("ORB_WHISTLE_HIGH_LOW_RATIO", "1.15"))
            ):
                self._last_whistle_summon_at = now
                self._emit({
                    "type": "cali_summon",
                    "source": "whistle",
                    "data": {
                        "peak_hz": round(peak_freq, 1),
                        "rms": round(rms, 5),
                        "tonal_ratio": round(tonal_ratio, 4),
                    },
                })
                return True
        except Exception as exc:
            print(f"Whistle summon detection error: {exc}", file=sys.stderr)
        return False

    def _is_cali_summon_request(self, text):
        normalized = re.sub(r"[^\w\s]", " ", str(text or "").lower())
        normalized = re.sub(r"\s+", " ", normalized).strip()
        if not normalized:
            return False
        return bool(
            re.search(r"\b(cali|orb|assistant)\s+(come here|come to me|over here|come back|return|come)\b", normalized)
            or re.search(r"\b(come here|come to me|over here|get over here|summon cali|call cali|cali here)\b", normalized)
        )

    def frame_text_with_acp(self, text, context=None):
        normalized = str(text or "").strip()
        return {"source": "text_input", "raw_input": text, "normalized_text": normalized, "transcript": normalized, "confidence": 1.0 if normalized else 0.0, "_source": "native_text_frame", "context": context or {}}

    def set_cali_orb_state(self, setting, value):
        if not self.cali:
            return False
        try:
            return self.cali.set_orb_state(setting, value)
        except Exception as e:
            print(f"CALI orb state error: {e}", file=sys.stderr)
            return False

    # --- Skills â€” preserved ---

    def _init_skill_library(self):
        if not CALI_SKILLS_AVAILABLE:
            return
        try:
            library_path = self.project_root / "cali_skills" / "library"
            self.skill_registry = SkillRegistry(str(library_path))
            self.skill_loader = SkillLoader(self.skill_registry)
            self.skill_arbitrator = SkillArbitrator(self.skill_loader)
            self.skill_memory = SkillMemoryBridge(str(self.project_root / "CALI_System" / "memory" / "cali_skills"))
            for skill in self.skill_registry.list_skills():
                self.skill_loader.activate(skill["id"])
            print(f"âœ“ CALI skill library online ({len(self.skill_loader.get_active())} active)", file=sys.stderr)
        except Exception as exc:
            self.skill_registry = None
            self.skill_loader = None
            self.skill_arbitrator = None
            self.skill_memory = None
            print(f"âš ï¸ CALI skill library init failed: {exc}", file=sys.stderr)

    def _ensure_decision_log(self):
        path = self.project_root / "CALI_System" / "memory" / "decisions.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)

    def handle_skill_request(self, text, input_frame=None):
        if not self.skill_registry or not self.skill_loader or not self.skill_arbitrator:
            return None
        normalized = str(text or "").strip()
        lowered = normalized.lower()
        if lowered in {"list skills", "cali list skills", "show skills", "skill status"}:
            skills = self.skill_registry.list_skills()
            active = sorted(self.skill_loader.get_active().keys())
            return {"response_text": f"{len(skills)} skills available. Active: {', '.join(active)}.", "skills": skills, "active": active}
        activate_match = re.search(r"\bactivate skill\s+([a-z0-9_\-]+)", lowered)
        if activate_match:
            skill_id = activate_match.group(1).replace("_skill", "")
            ok = self.skill_loader.activate(skill_id)
            return {"response_text": f"Skill {skill_id} {'activated' if ok else 'not found'}.", "skill_id": skill_id, "activated": ok}
        deactivate_match = re.search(r"\bdeactivate skill\s+([a-z0-9_\-]+)", lowered)
        if deactivate_match:
            skill_id = deactivate_match.group(1).replace("_skill", "")
            self.skill_loader.deactivate(skill_id)
            return {"response_text": f"Skill {skill_id} deactivated.", "skill_id": skill_id, "deactivated": True}
        research_terms = ("research", "look up", "latest", "current", "verify", "fact check")
        if any(term in lowered for term in research_terms):
            return None
        ranked = self.skill_arbitrator.select_skill(normalized, {"input_frame": input_frame or {}, "memory": self.skill_memory, "current_topic": self.current_note_topic})
        if not ranked or ranked[0]["confidence"] < 0.65:
            return None
        command = "explain"
        if any(term in lowered for term in ("start", "launch")):
            command = "start_service"
        elif "list sites" in lowered:
            command = "list_sites"
        elif "sha256" in lowered or "hash" in lowered:
            command = "sha256"
        result = self.skill_arbitrator.execute_best(intent=normalized, command=command, params={"text": normalized}, context={"input_frame": input_frame or {}, "memory": self.skill_memory, "current_topic": self.current_note_topic})
        response_text = result.get("result") or result.get("error") or result.get("status")
        if not isinstance(response_text, str):
            response_text = json.dumps(response_text, ensure_ascii=False, default=str)
        result["response_text"] = response_text
        return result

    # --- Desktop presence / swarm â€” preserved ---

    def _init_desktop_presence(self):
        enabled_env = os.getenv("ORB_ENABLE_DESKTOP_PRESENCE")
        if enabled_env is None:
            enabled = ENABLE_PRESENCE_DEFAULT or self._legacy_presence_flag()
        else:
            enabled = enabled_env.strip().lower() in {"1", "true", "yes", "on"}
        if not enabled:
            print("Desktop presence disabled (safe mode)", file=sys.stderr)
            return
        if not DESKTOP_PRESENCE_AVAILABLE:
            print("Desktop presence module unavailable", file=sys.stderr)
            return
        if not self.controller:
            print("Desktop presence not started (controller unavailable)", file=sys.stderr)
            return
        try:
            presence_db = os.getenv("ORB_PRESENCE_DB", str(self.system_root / "vault_system" / "behavior_learner.db"))
            self.desktop_presence = DesktopPresence(orb_controller=self, db_path=presence_db)
            self.desktop_presence.start_background()
            print("âœ“ Desktop presence memory online", file=sys.stderr)
        except Exception as exc:
            self.desktop_presence = None
            print(f"[Presence Disabled] {exc}", file=sys.stderr)

    def _legacy_presence_flag(self):
        return os.getenv("ENABLE_PRESENCE", "").strip().lower() in {"1", "true", "yes", "on"}

    def _init_swarm_extension(self):
        enabled_env = os.getenv("ORB_ENABLE_SWARM_EXTENSION")
        if enabled_env is None:
            enabled = ENABLE_SWARM_EXTENSION_DEFAULT or self._legacy_swarm_flag()
        else:
            enabled = enabled_env.strip().lower() in {"1", "true", "yes", "on"}
        if not enabled:
            print("Swarm extension disabled (safe mode)", file=sys.stderr)
            return
        if not SWARM_EXTENSION_AVAILABLE:
            print("Swarm extension module unavailable", file=sys.stderr)
            return
        if not self.controller:
            print("Swarm extension not started (controller unavailable)", file=sys.stderr)
            return
        try:
            self.swarm_extension = CaliSwarmExtensionRuntime(controller=self.controller, system_root=self.system_root)
            self.swarm_extension.start_background()
            if hasattr(self.controller, "attach_swarm_extension"):
                self.controller.attach_swarm_extension(self.swarm_extension)
            print("âœ“ Swarm extension runtime online", file=sys.stderr)
        except Exception as exc:
            self.swarm_extension = None
            print(f"[Swarm Extension Disabled] {exc}", file=sys.stderr)

    def _legacy_swarm_flag(self):
        return os.getenv("ENABLE_SWARM_EXTENSION", "").strip().lower() in {"1", "true", "yes", "on"}

    # --- Emotion / presence / cognitive helpers â€” preserved ---

    def _emotion_from_reasoning(self, reasoning):
        if not reasoning:
            return "thoughtful_warm"
        advisory = reasoning.get("advisory_verdict", {})
        confidence = advisory.get("confidence", 0.5)
        if confidence >= 0.8:
            return "confident"
        if confidence <= 0.45:
            return "uncertain"
        if advisory.get("tension_detected"):
            return "analytical"
        return "thoughtful_warm"

    def _presence_profile_from_stimulus(self, stimulus):
        payload = stimulus or {}
        context = payload.get("presence_context") or {}
        meta = payload.get("meta") or {}
        event = str(meta.get("event") or "").lower()
        idle_seconds = int(context.get("idle_seconds") or meta.get("idle_seconds") or 0)
        is_idle = payload.get("type") == "idle_reflection" or event == "idle_start" or idle_seconds >= 30
        autonomy_level = 0.94 if is_idle else 0.82
        return {"is_idle": is_idle, "idle_seconds": idle_seconds, "autonomy_level": autonomy_level, "cursor_influence": "minimal" if is_idle else "low", "movement_intent": "free_float", "quadrant": context.get("quadrant"), "active_process": context.get("active_process"), "active_window": context.get("active_window")}

    def _to_ratio(self, raw_value, fallback=0.0):
        try:
            numeric = float(raw_value)
        except Exception:
            return float(fallback)
        if numeric > 1.0:
            numeric = numeric / 100.0
        return max(0.0, min(1.0, numeric))

    def _build_presence_update(self, stimulus, cognitive):
        payload = stimulus or {}
        context = payload.get("presence_context") or {}
        meta = payload.get("meta") or {}
        profile = self._presence_profile_from_stimulus(payload)
        advisory = cognitive.get("advisory_verdict", {}) if isinstance(cognitive, dict) else {}
        confidence = advisory.get("confidence")
        if confidence is None and isinstance(cognitive, dict):
            confidence = cognitive.get("confidence")
        if confidence is None:
            confidence = profile.get("autonomy_level", 0.82)
        event_name = str(meta.get("event") or payload.get("type") or "presence")
        if event_name == "desktop_context":
            event_name = "context_update"
        return {"type": "presence_update", "schema_version": "1.0", "ts": float(context.get("timestamp") or time.time()), "idle": bool(profile.get("is_idle")), "idle_seconds": int(profile.get("idle_seconds") or 0), "active_window": str(context.get("active_window") or "unknown"), "active_process": str(context.get("active_process") or "unknown"), "cpu": self._to_ratio(context.get("system_load"), fallback=0.0), "memory": self._to_ratio(context.get("memory_usage"), fallback=0.0), "cognitive_mode": str(cognitive.get("cognitive_mode", "DEDUCTIVE")) if isinstance(cognitive, dict) else "DEDUCTIVE", "autonomy_level": float(profile.get("autonomy_level") or 0.82), "confidence_state": max(0.0, min(1.0, float(confidence))), "last_event": event_name, "quadrant": context.get("quadrant"), "stimulus_type": str(payload.get("type") or ""), "cursor_influence": profile.get("cursor_influence"), "movement_intent": profile.get("movement_intent")}

    def _emit_presence_pulse(self, stimulus, thought):
        stype = str((stimulus or {}).get("type", ""))
        if stype not in {"desktop_context", "idle_transition", "idle_reflection"}:
            return
        cognitive = None
        if thought is not None:
            try:
                cognitive = thought.pulse() if hasattr(thought, "pulse") else thought
            except Exception:
                cognitive = None
        update = self._build_presence_update(stimulus, cognitive)
        self.latest_presence_update = update
        self._emit(update)

    def cognitively_emerge(self, stimulus):
        if not self.controller:
            return None
        thought = self.controller.cognitively_emerge(stimulus)
        self._emit_presence_pulse(stimulus, thought)
        return thought

    def idle_cognition(self, stimulus):
        if not self.controller:
            return None
        if hasattr(self.controller, "idle_cognition"):
            thought = self.controller.idle_cognition(stimulus)
        else:
            thought = self.controller.cognitively_emerge(stimulus)
        self._emit_presence_pulse(stimulus, thought)
        return thought

    def _emit(self, payload):
        with self._emit_lock:
            print(json.dumps(payload), flush=True)

    # --- Speech recognition â€” preserved ---

    def start_speech_recognition(self):
        if not self._ensure_mic_runtime():
            return False
        if self.speech_thread and self.speech_thread.is_alive():
            return True
        self.speech_thread = threading.Thread(target=self._speech_loop)
        self.speech_thread.daemon = True
        self.speech_thread.start()
        return True

    def set_speech_recognition(self, enabled):
        if enabled and not self._ensure_mic_runtime():
            return False
        if not self.audio_runtime.get_mic():
            return False
        self.speech_enabled = bool(enabled)
        if self.speech_enabled:
            self.start_speech_recognition()
        self._emit({"type": "listening_mode", "data": {"enabled": self.speech_enabled, "mode": "continuous"}})
        return True

    def listen_once(self):
        if not self._ensure_mic_runtime():
            return False
        if self.speech_lock.locked():
            return False
        if self.listen_once_thread and self.listen_once_thread.is_alive():
            return False
        self.listen_once_thread = threading.Thread(target=self._capture_speech_chunk, kwargs={"mode": "oneshot"}, daemon=True)
        self.listen_once_thread.start()
        return True

    def _capture_speech_chunk(self, mode="continuous"):
        mic = self.audio_runtime.get_mic()
        if not mic:
            return None
        if not self.speech_lock.acquire(blocking=False):
            return None
        try:
            self._emit({"type": "listening_state", "data": {"listening": True, "mode": mode}})
            import soundfile as sf
            audio_data = mic.record_chunk()
            if self._detect_whistle_summon(audio_data, mic.sample_rate):
                return ""
            cali_hearing = self.hear_with_cali(audio_data.flatten())
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                temp_path = temp_file.name
                sf.write(temp_path, audio_data.flatten(), mic.sample_rate)
            try:
                hearing_result = mic.processor.hear(temp_path, context={"source": "orb_microphone", "mode": mode})
                transcription = hearing_result.get("transcript", "") if isinstance(hearing_result, dict) else str(hearing_result or "")
                if transcription and transcription.strip():
                    print(f"ðŸŽ¤ Heard: {transcription}", file=sys.stderr)
                    self._emit({"type": "speech_heard", "data": {"transcript": transcription}})
                    if self._is_cali_summon_request(transcription):
                        self._emit({"type": "cali_summon", "source": "voice", "data": {"transcript": transcription}})
                        return transcription
                    self.emit_latency_mask_speech()
                    _align = self.alignment_layer.filter(transcription, {"source": "speech_input"})
                    if not _align["allowed"]:
                        print(f"âš ï¸ Speech input blocked by alignment layer: {_align['code']}", file=sys.stderr)
                        return None
                    transcription = _align["sanitized"]
                    try:
                        record_runtime_voice_observation(transcript=transcription, source="orb_microphone", metadata={"mode": mode, "origin": "floating_assistant_orb"})
                    except Exception as exc:
                        print(f"Legacy voice observation write failed: {exc}", file=sys.stderr)
                    vault_command = self.handle_research_vault_command(transcription)
                    if vault_command:
                        self.emit_spoken_text(vault_command["response_text"])
                        self._emit({"type": "research_vault_result", "data": vault_command})
                        return transcription
                    skill_result = self.handle_skill_request(transcription)
                    if skill_result:
                        self.emit_spoken_text(skill_result["response_text"])
                        self._emit({"type": "skill_result", "data": skill_result})
                        return transcription
                    core_result = self.handle_core_knowledge_request(transcription)
                    if core_result:
                        self.emit_spoken_text(core_result["response_text"])
                        self._emit({"type": "core_knowledge_result", "data": core_result})
                        return transcription
                    recall_result = self.handle_recall_request(transcription)
                    if recall_result:
                        self.emit_spoken_text(recall_result["response_text"])
                        self._emit({"type": "query_result", "data": recall_result})
                        return transcription
                    note_result = self.handle_note_request(transcription, source="voice")
                    if note_result:
                        return transcription
                    self._process_verbal_command(transcription)
                    stimulus = {"type": "speech_query", "content": transcription, "coordinates": [0, 0], "velocity": 0.0}
                    thought = self.cognitively_emerge(stimulus)
                    intent = self.detect_research_intent(transcription)
                    research = None
                    cali_reasoning = None
                    if intent.get("is_research"):
                        research = self.run_research_request(transcription, intent.get("domains") or [])
                        response_text = research.get("response_text") or research.get("voice_response")
                    else:
                        cali_reasoning = self.reason_with_cali(transcription, context={"source": "speech_query", "stimulus_type": "speech_query"})
                        response_text = cali_reasoning.get("recommended_response") if cali_reasoning else f"I heard you say: {transcription}"
                    spoken_response_text = self._voice_budget_text(response_text)
                    voice_payload = self.build_voice_payload(spoken_response_text, "analytical" if research else self._emotion_from_reasoning(cali_reasoning))
                    voice_payload["spoken_text"] = spoken_response_text
                    self.last_response_text = response_text or ""
                    if thought:
                        pulse = thought.pulse() if hasattr(thought, "pulse") else thought
                        pulse["field_density"] = getattr(thought, "logic_validity", {}).get("field_density", 0)
                        ucm = getattr(thought, "ucm_envelope", None) or {}
                        flags = (ucm.get("cali_reflection") or {}).get("flags", {})
                        pulse["drift_detected"] = flags.get("drift_detected", False)
                        if getattr(thought, "epistemic_traces", None):
                            pulse["four_mind"] = {mind: round(data.get("confidence", 0.5), 3) for mind, data in thought.epistemic_traces.items()}
                        pulse["egf_state"] = getattr(thought, "egf_visual_state", None)
                        self._emit({"type": "speech_pulse", "data": pulse, "transcription": transcription, "intent": intent, "response_text": response_text, "audio_path": voice_payload.get("audio_path"), "audio_url": voice_payload.get("audio_url"), "voice_package": voice_payload.get("voice_package"), "tts_provider": voice_payload.get("tts_provider"), "tts_fallback_used": voice_payload.get("tts_fallback_used"), "qwen_tts_endpoint": voice_payload.get("qwen_tts_endpoint"), "cp3_invoked": voice_payload.get("cp3_invoked"), "audio_error": voice_payload.get("audio_error"), "research": research, "cali_reasoning": cali_reasoning, "advisory_verdict": cali_reasoning.get("advisory_verdict") if cali_reasoning else None, "cali_hearing": cali_hearing})
                    else:
                        self._emit({"type": "speech_pulse", "data": {}, "transcription": transcription, "intent": intent, "response_text": response_text, "audio_path": voice_payload.get("audio_path"), "audio_url": voice_payload.get("audio_url"), "voice_package": voice_payload.get("voice_package"), "tts_provider": voice_payload.get("tts_provider"), "tts_fallback_used": voice_payload.get("tts_fallback_used"), "qwen_tts_endpoint": voice_payload.get("qwen_tts_endpoint"), "cp3_invoked": voice_payload.get("cp3_invoked"), "audio_error": voice_payload.get("audio_error"), "research": research, "cali_reasoning": cali_reasoning, "advisory_verdict": cali_reasoning.get("advisory_verdict") if cali_reasoning else None, "cali_hearing": cali_hearing})
                    return transcription
                return ""
            finally:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
        except Exception as e:
            print(f"Speech processing error: {e}", file=sys.stderr)
            time.sleep(1)
            return None
        finally:
            self._emit({"type": "listening_state", "data": {"listening": False, "mode": mode}})
            self.speech_lock.release()

    def _speech_loop(self):
        while self.running:
            if not self.speech_enabled:
                time.sleep(0.05)
                continue
            self._capture_speech_chunk(mode="continuous")
            time.sleep(0.1)

    def _process_verbal_command(self, transcription):
        if not transcription.lower().startswith("cali"):
            return
        command = transcription.lower()[5:].strip()
        if "slow down" in command:
            self._emit({"type": "verbal_command", "command": "slow_down"})
            self.emit_spoken_text("Slowing down")
        elif "speed up" in command:
            self._emit({"type": "verbal_command", "command": "speed_up"})
            self.emit_spoken_text("Speeding up")
        elif "change color" in command:
            color = "#00ff88"
            if "blue" in command:
                color = "#00ff88"
            elif "red" in command:
                color = "#ff4444"
            elif "green" in command:
                color = "#44ff44"
            self._emit({"type": "verbal_command", "command": "change_color", "color": color})
            self.emit_spoken_text("Changing color")
        elif "increase size" in command:
            self._emit({"type": "verbal_command", "command": "increase_size"})
            self.emit_spoken_text("Increasing size")
        elif "decrease size" in command:
            self._emit({"type": "verbal_command", "command": "decrease_size"})
            self.emit_spoken_text("Decreasing size")
        elif "dock" in command:
            self._emit({"type": "verbal_command", "command": "dock_orb"})
            self.emit_spoken_text("Docking")
        elif "front and center" in command or "launch orb" in command or "show orb" in command:
            self._emit({"type": "verbal_command", "command": "show_orb"})
            self.emit_spoken_text("Front and center")
        elif "toggle orb" in command:
            self._emit({"type": "verbal_command", "command": "toggle_visibility"})
            self.emit_spoken_text("Toggling")

    # --- Lifecycle â€” start / stop / cursor / cognitive loops â€” preserved ---

    def stop(self):
        self.running = False
        self.speech_enabled = False
        cognitive_thread = getattr(self, "cognitive_thread", None)
        speech_thread = getattr(self, "speech_thread", None)
        listen_once_thread = getattr(self, "listen_once_thread", None)
        if cognitive_thread:
            cognitive_thread.join(timeout=1)
        if speech_thread:
            speech_thread.join(timeout=1)
        if listen_once_thread:
            listen_once_thread.join(timeout=1)
        if self.desktop_presence:
            try:
                self.desktop_presence.graceful_shutdown()
            except Exception:
                pass
        if self.swarm_extension:
            try:
                self.swarm_extension.shutdown()
            except Exception:
                pass
        if self.cali:
            self.cali.close()
        if self.controller and hasattr(self.controller, "shutdown"):
            try:
                self.controller.shutdown()
            except Exception:
                pass

    def process_cursor_movement(self, x, y):
        current_time = time.time()
        dx = x - self.last_cursor_pos[0]
        dy = y - self.last_cursor_pos[1]
        dt = current_time - self.last_time
        velocity = ((dx**2 + dy**2) ** 0.5) / max(dt, 0.001) if dt > 0 else 0
        self.last_cursor_pos = (x, y)
        self.last_time = current_time
        stimulus = {"type": "cursor_movement", "coordinates": [x, y], "velocity": min(velocity, 50.0), "intent": "navigation"}
        thought = self.cognitively_emerge(stimulus)
        if thought:
            if hasattr(thought, "pulse"):
                pulse = thought.pulse()
                pulse["field_density"] = getattr(thought, "logic_validity", {}).get("field_density", 0)
                ucm = getattr(thought, "ucm_envelope", None) or {}
                flags = (ucm.get("cali_reflection") or {}).get("flags", {})
                pulse["drift_detected"] = flags.get("drift_detected", False)
                if getattr(thought, "epistemic_traces", None):
                    pulse["four_mind"] = {mind: round(data.get("confidence", 0.5), 3) for mind, data in thought.epistemic_traces.items()}
                pulse["egf_state"] = getattr(thought, "egf_visual_state", None)
            else:
                pulse = thought
            response = {"type": "cognitive_pulse", "data": pulse}
            print(json.dumps(response), flush=True)
            egf_state = pulse.get("egf_state") if isinstance(pulse, dict) else None
            if isinstance(egf_state, dict):
                print(json.dumps({"type": "egf_state", "data": egf_state}), flush=True)
            return pulse
        return None

    def _cognitive_loop(self):
        while self.running:
            time.sleep(0.1)

    def _cognitive_semantic_tag(self):
        mode = ""
        if self.latest_presence_update:
            mode = str(self.latest_presence_update.get("cognitive_mode", "")).upper()
        if "INTUITION" in mode:
            return "intuiting"
        if "HABIT" in mode:
            return "habituating"
        if "GUARD" in mode:
            return "guarding"
        if "DEDUCTIVE" in mode:
            return "reasoning"
        return "idle"

    def _build_hlsf_snapshot(self):
        snapshot = {"position": [0.0, 0.0], "active_dims": [], "hysteresis": {"trigger": 800, "release": 650, "active": False, "density_ratio": 0.0}, "field_density": 0, "semantic_tag": self._cognitive_semantic_tag()}
        if not (self.controller and hasattr(self.controller, "engine")):
            return snapshot
        try:
            engine = self.controller.engine
            field_map = engine.field_map
            density = len(field_map)
            snapshot["field_density"] = density
            trigger = engine.purge_trigger_threshold
            release = engine.purge_release_threshold
            snapshot["hysteresis"] = {"trigger": trigger, "release": release, "active": bool(engine.edge_cutter_active), "density_ratio": round(density / trigger, 3) if trigger > 0 else 0.0}
            if field_map:
                top_nodes = sorted(field_map.values(), key=lambda n: n.cognitive_load, reverse=True)[:3]
                snapshot["active_dims"] = [{"n": n.n, "k": n.k, "energy": round(min(n.cognitive_load / 10.0, 1.0), 3), "x": round(n.coordinates[0], 4) if len(n.coordinates) > 0 else 0.0, "y": round(n.coordinates[1], 4) if len(n.coordinates) > 1 else 0.0} for n in top_nodes]
                cx = sum(d["x"] * d["energy"] for d in snapshot["active_dims"])
                cy = sum(d["y"] * d["energy"] for d in snapshot["active_dims"])
                total_e = sum(d["energy"] for d in snapshot["active_dims"]) or 1.0
                snapshot["position"] = [round(cx / total_e, 4), round(cy / total_e, 4)]
        except Exception as e:
            print(f"HLSF snapshot build error: {e}", file=sys.stderr)
        return snapshot

    def _hlsf_emit_loop(self):
        while self.running:
            try:
                snap = self._build_hlsf_snapshot()
                self._emit({"type": "hlsf_snapshot", "data": snap})
            except Exception as e:
                print(f"HLSF emit loop error: {e}", file=sys.stderr)
            time.sleep(2)

    def _write_mesh_heartbeat(self):
        mesh_root = os.getenv("ORB_SHARED_MESH_ROOT", "").strip()
        if not mesh_root:
            return
        try:
            snapshots_dir = Path(mesh_root) / "exports" / self.instance_id / "state_snapshots"
            snapshots_dir.mkdir(parents=True, exist_ok=True)
            snap = self._build_hlsf_snapshot()
            heartbeat = {"instance_id": self.instance_id, "ts": time.time(), "running": self.running, "controller_status": "active" if self.controller else "inactive", "listening_enabled": self.speech_enabled, "hlsf": snap}
            (snapshots_dir / "heartbeat.json").write_text(json.dumps(heartbeat, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"Mesh heartbeat write failed: {e}", file=sys.stderr)

    def _heartbeat_loop(self):
        while self.running:
            self._write_mesh_heartbeat()
            self.orb_heartbeat.set_provider_status("active" if self.controller else "inactive")
            self.orb_heartbeat.set_cognition_mode("speech_active" if self.speech_enabled else "deterministic")
            time.sleep(60)

    def start(self):
        self.running = True
        self.cognitive_thread = threading.Thread(target=self._cognitive_loop)
        self.cognitive_thread.daemon = True
        self.cognitive_thread.start()
        self.hlsf_emit_thread = threading.Thread(target=self._hlsf_emit_loop)
        self.hlsf_emit_thread.daemon = True
        self.hlsf_emit_thread.start()
        self._write_mesh_heartbeat()
        self.heartbeat_thread = threading.Thread(target=self._heartbeat_loop)
        self.heartbeat_thread.daemon = True
        self.heartbeat_thread.start()
        self.orb_heartbeat.set_provider_status("active" if self.controller else "inactive")
        self.orb_heartbeat.set_permissions(["voice", "presence", "research"] if self.speech_enabled else ["presence", "research"])
        self.orb_heartbeat.start()
        self.orb_heartbeat.emit_now()
        if self.auto_listen:
            self.set_speech_recognition(True)

    def get_status(self):
        cali_root = self.project_root / "CALI_System"
        memory_root = cali_root / "memory"
        voice_cache_root = cali_root / "voice_cache"
        logs_root = self.project_root / "logs"
        decisions_path = memory_root / "decisions.jsonl"
        short_term_cache_path = memory_root / "short_term_cache.db"
        last_decision = None
        if decisions_path.exists():
            try:
                decision_lines = [line.strip() for line in decisions_path.read_text(encoding="utf-8").splitlines() if line.strip()]
                if decision_lines:
                    last_decision = json.loads(decision_lines[-1])
            except Exception:
                last_decision = None

        now = datetime.now().isoformat()

        # Normalize cp3_io
        cp3_io = dict(self.audio_runtime.audio_runtime_status)
        cp3_io.setdefault("cp3_root", str(CP3_PATH))
        cp3_io.setdefault("cp3_root_exists", CP3_PATH.exists())
        cp3_io.setdefault("voice_runtime_ready", False)
        cp3_io.setdefault("speech_runtime_ready", False)
        cp3_io.setdefault("text_framing_available", False)
        cp3_io.setdefault("state", "UNKNOWN")
        cp3_io.setdefault("ready", False)
        cp3_io.setdefault("last_error", "")
        cp3_io.setdefault("last_updated", now)
        cp3_io["adapter_import_status"] = AUDIO_IMPORT_STATUS
        cp3_io["adapter_import_error"] = AUDIO_IMPORT_ERROR
        cp3_io["audio_runtime_status"] = dict(self.audio_runtime.audio_runtime_status)
        cp3_io["speech_adapter_available"] = self.audio_runtime.audio_runtime_status.get("speech") != "unavailable"
        cp3_io["speech_runtime_ready"] = self.audio_runtime.get_mic() is not None
        cp3_io["voice_adapter_available"] = self.audio_runtime.audio_runtime_status.get("voice") != "unavailable"
        cp3_io["voice_runtime_ready"] = self.audio_runtime.get_voice() is not None
        cp3_io["text_framing_available"] = True
        cp3_io["audio_input_source"] = "orb_microphone"
        cp3_io["text_input_source"] = "ipc_query"
        cp3_io["listening_enabled"] = self.speech_enabled

        # Normalize local_llm
        local_llm = dict(self.last_local_llm_health)
        local_llm.setdefault("endpoint", self._active_local_endpoint())
        local_llm.setdefault("model", self._active_local_model())
        local_llm.setdefault("route", self.cali.orb_state.get("llm_route") if self.cali else os.getenv("ORB_LLM_ROUTE", "local"))
        local_llm["governance_wrapper"] = False
        local_llm.setdefault("ready", False)
        local_llm.setdefault("state", "UNKNOWN")
        local_llm.setdefault("last_error", "")
        local_llm.setdefault("last_updated", now)
        local_llm["ollama_keep_alive"] = os.getenv("CALI_OLLAMA_KEEP_ALIVE", os.getenv("OLLAMA_KEEP_ALIVE", "15m"))
        local_llm["requested_gpu_layers"] = self._ollama_gpu_options().get("num_gpu")
        local_llm["last_runtime"] = dict(self.llm_client.last_llm_runtime)

        # Normalize qwen_tts
        qwen_tts = dict(self.last_qwen_tts_health)
        qwen_tts.setdefault("endpoint", self._active_qwen_tts_endpoint())
        qwen_tts.setdefault("realtime_endpoint", os.getenv("ORB_REALTIME_TTS_BASE_URL"))
        qwen_tts.setdefault("provider", os.getenv("ORB_REALTIME_TTS_ENGINE", os.getenv("ORB_TTS_PROVIDER", "cosyvoice-stream")))
        qwen_tts.setdefault("ready", False)
        qwen_tts.setdefault("state", "UNKNOWN")
        qwen_tts.setdefault("last_error", "")
        qwen_tts.setdefault("last_updated", now)
        def refresh_runtime_health(self):
            """Refresh health status for local_llm and qwen_tts in a non-blocking/background way if needed."""
            try:
                self.last_local_llm_health = self._probe_local_llm_health()
            except Exception as exc:
                self.last_local_llm_health = {"ready": False, "endpoint": self._active_local_endpoint(), "model": self._active_local_model(), "error": str(exc)}
            try:
                self.last_qwen_tts_health = self._probe_qwen_tts_health()
            except Exception as exc:
                self.last_qwen_tts_health = {"ready": False, "endpoint": self._active_qwen_tts_endpoint(), "error": str(exc)}
        def start(self):
            # ...existing code...
            super().start() if hasattr(super(), 'start') else None
            import threading
            threading.Thread(target=self.refresh_runtime_health, daemon=True).start()
            # ...existing code...
    def refresh_runtime_health(self):
        """Refresh health status for local_llm and qwen_tts in a non-blocking/background way if needed."""
        try:
            self.last_local_llm_health = self._probe_local_llm_health()
        except Exception as exc:
            self.last_local_llm_health = {"ready": False, "error": str(exc)}
        try:
            self.last_qwen_tts_health = self._probe_qwen_tts_health()
        except Exception as exc:
            self.last_qwen_tts_health = {"ready": False, "error": str(exc)}

        status = {
            "instance_id": self.instance_id,
            "running": self.running,
            "controller_status": "active" if self.controller else "inactive",
            "listening_enabled": self.speech_enabled,
            "auto_listen": self.auto_listen,
            "project_root": str(self.project_root),
            "system_root": str(self.system_root),
            "shared_mesh_root": self.shared_mesh_root,
            "notes": {
                "base_path": str(self.cali_notes.base_path),
                "active_topic": self.current_note_topic,
                "active_session": str(self.current_note_session) if self.current_note_session else None,
                "taking_notes": self.note_taking_enabled,
                "pending_notepad_summary": bool(self.pending_notepad_summary),
                "last_notepad_path": self.last_notepad_path,
            },
            "core_knowledge": {
                "base_path": str(self.core_knowledge.base_path) if self.core_knowledge else None,
                "available": bool(self.core_knowledge),
            },
            "skills": {
                "available": bool(self.skill_registry),
                "catalog_count": len(self.skill_registry.catalog) if self.skill_registry else 0,
                "active": sorted(self.skill_loader.get_active().keys()) if self.skill_loader else [],
                "last_decision": last_decision,
            },
            "research_vault": {
                "active_path": str(self.research_vault.active_path) if self.research_vault else None,
                "index_path": str(self.research_vault.index_path) if self.research_vault else None,
                "available": bool(self.research_vault),
            },
            "substrate": build_substrate_status(self),
            "cp3_io": cp3_io,
            "local_llm": local_llm,
            "qwen_tts": qwen_tts,
            "services": {
                "domains": [service.get("domain") for service in self.load_service_manifest()],
                "items": [
                    {**service, "service_status": self.service_status_cache.get(str(service.get("service_id") or service.get("id"))) or self._service_status(service, probe_network=False)}
                    for service in self.load_service_manifest()
                ],
                "manifest_path": str(self.core_knowledge.base_path / "spruked" / "services.json") if self.core_knowledge else None,
                "mode": "local_manifest_required",
            },
            "awareness_permissions": {
                "desktop_presence_enabled": str(os.getenv("ORB_ENABLE_DESKTOP_PRESENCE", "")).strip().lower() in {"1", "true", "yes", "on"},
                "browser_awareness_enabled": str(os.getenv("ORB_ENABLE_BROWSER_AWARENESS", "1")).strip().lower() in {"1", "true", "yes", "on"},
            },
            "site_orb_status": self.site_orb_status,
        }
        status["acp_io"] = build_legacy_acp_io(cp3_io)

        if self.cali:
            status["cali_status"] = self.cali.get_status()
        if self.desktop_presence:
            status["desktop_presence"] = self.desktop_presence.get_status()
        else:
            status["desktop_presence"] = {"running": False}
        if self.latest_presence_update:
            status["presence_update"] = self.latest_presence_update

        runtime_snapshot = build_runtime_snapshot(
            self,
            cali_status=status.get("cali_status") or {},
            presence_status=status.get("desktop_presence") or {},
            presence_update=status.get("presence_update") or {},
            local_llm=local_llm,
            qwen_tts=qwen_tts,
            cp3_io=cp3_io,
            audio_runtime=cp3_io,
            controller=self.controller,
        )
        # Ensure required keys
        for k in ("active_llm", "llm_connected", "qwen_tts_ready", "voice_ready", "last_error", "last_updated"):
            runtime_snapshot.setdefault(k, None)
        status["runtime_snapshot"] = runtime_snapshot

        if self.controller and getattr(self.controller, "gravity_bridge", None):
            try:
                status["egf_state"] = self.controller.gravity_bridge.get_visual_state()
            except Exception as exc:
                status["egf_state"] = {"type": "egf_state", "ok": False, "mode": "fault", "error": str(exc)}
        if self.swarm_extension:
            status["swarm_extension"] = self.swarm_extension.get_status()
        else:
            status["swarm_extension"] = {"running": False}
        return status


__all__ = ["CALIFloatingOrb"]


def _main() -> None:
    """Run Orb and respond to simple IPC messages over stdin/stdout (JSON lines)."""
    orb = CALIFloatingOrb(PROJECT_ROOT)
    orb.start()

    if os.getenv("ORB_ENABLE_UCM_STATUS_CHECK", "0").strip().lower() in {"1", "true", "yes", "on"}:
        try:
            with urllib.request.urlopen("http://localhost:5050/orb/status", timeout=5) as response:
                data = json.loads(response.read().decode())
                if data.get("status") == "active":
                    print("UCM status active", file=sys.stderr)
                else:
                    print("UCM status not active", file=sys.stderr)
        except Exception as e:
            print(f"UCM status check failed: {e}", file=sys.stderr)

    print(json.dumps({
        "type": "ready",
        "orb_standard_version": "1.0.0",
        "orb_shell": os.getenv("ORB_SHELL", "desktop"),
        "cp3_status": {
            "cp3_root_set": bool(os.getenv("CP3_ROOT")),
            "audio_runtime": orb.audio_runtime.audio_runtime_status,
            "speech_available": orb.audio_runtime.audio_runtime_status.get("speech") != "unavailable",
            "tts_available": orb.audio_runtime.audio_runtime_status.get("voice") != "unavailable",
            "audio_import_status": AUDIO_IMPORT_STATUS,
        },
        "alignment_layer": "active",
        "primitive_cache": "active",
    }), flush=True)

    def _emit_with_compliance(payload_type, request_id, data, visitor_input="", intent=None, lead_payload=None, orb_profile="website_orb"):
        voice_payload = {
            "audio_path": data.get("audio_path"),
            "audio_url": data.get("audio_url"),
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
        enriched = dict(data)
        enriched["compliance"] = compliance
        enriched["site_orb_status"] = orb.site_orb_status
        orb._emit({"type": payload_type, "request_id": request_id, "data": enriched})

    for line in sys.stdin:
        try:
            msg = json.loads(line.strip())
        except Exception:
            continue

        msg_type = msg.get("type")
        request_id = msg.get("request_id")

        if msg_type == "shutdown":
            orb.stop()
            print(json.dumps({"type": "shutdown_ack", "request_id": request_id}), flush=True)
            break

        elif msg_type == "cursor_move":
            x = msg.get("x", 0)
            y = msg.get("y", 0)
            orb.process_cursor_movement(x, y)

        elif msg_type == "get_status":
            status = orb.get_status()
            response = {"type": "status_response", "request_id": request_id, "data": status}
            print(json.dumps(response), flush=True)

        elif msg_type == "service_control":
            result = orb.handle_service_control(msg.get("service_id") or msg.get("service"), msg.get("action") or "status")
            response = {"type": "service_result", "request_id": request_id, "data": result}
            print(json.dumps(response), flush=True)

        elif msg_type == "listen_once":
            accepted = orb.listen_once()
            orb._emit({"type": "listen_once_ack", "request_id": request_id, "data": {"accepted": accepted}})

        elif msg_type == "set_listening":
            enabled = bool(msg.get("enabled", False))
            ok = orb.set_speech_recognition(enabled)
            orb._emit({"type": "listening_mode", "request_id": request_id, "data": {"enabled": orb.speech_enabled if ok else False, "ok": ok, "mode": "continuous"}})

        elif msg_type == "query":
            text = msg.get("text", "")
            _align = orb.alignment_layer.filter(text, {"source": "ipc_query"})
            if not _align["allowed"]:
                _emit_with_compliance(
                    "query_result",
                    request_id,
                    {"echo": text, "response_text": _align["reason"], "alignment_blocked": True, "alignment_code": _align["code"]},
                    visitor_input=text,
                    intent={"reason": "alignment_blocked"},
                )
                continue
            text = _align["sanitized"]

            _primitive = orb.primitive_cache.resolve(text)
            if _primitive:
                orb.last_response_text = _primitive["response_text"]
                _p_voice = orb.build_voice_payload(_primitive["response_text"], _primitive["emotion"])
                _emit_with_compliance(
                    "query_result",
                    request_id,
                    {"echo": text, "response_text": _primitive["response_text"], "audio_path": _p_voice.get("audio_path"), "voice_package": _p_voice.get("voice_package"), "_route_meta": primitive_meta(_primitive["entry_id"])},
                    visitor_input=text,
                    intent={"reason": "primitive"},
                )
                orb.orb_heartbeat.record_route("primitive")
                continue

            _ci = orb.detect_current_info_intent(text)
            if _ci["is_current_info"]:
                _ci_text = "I don't have access to live data right now. I can't check the current weather, prices, or real-time feeds without a connected tool."
                orb.last_response_text = _ci_text
                _ci_voice = orb.build_voice_payload(_ci_text)
                _emit_with_compliance(
                    "query_result",
                    request_id,
                    {"echo": text, "response_text": _ci_text, "audio_path": _ci_voice.get("audio_path"), "voice_package": _ci_voice.get("voice_package"), "_route_meta": make_route_meta(provider_selected="tool_router", provider_used="unsupported_tool_response", cognition_mode="deterministic", intent="current_info", fallback_reason="no_live_tool_connected", bypassed_provider=True, bypassed_governance=True, route_class="tool", extra={"current_info_signal": _ci["signal"]})},
                    visitor_input=text,
                    intent={"reason": "current_info"},
                )
                orb.orb_heartbeat.record_route("current_info_unsupported")
                continue

            input_frame = orb.frame_text_with_acp(text, context={"source": "ipc_query", "stimulus_type": "text_query"})
            framed_text = input_frame.get("normalized_text") or input_frame.get("transcript") or text

            vault_command = orb.handle_research_vault_command(framed_text)
            if vault_command:
                voice_payload = orb.build_voice_payload(vault_command["response_text"])
                _emit_with_compliance(
                    "query_result",
                    request_id,
                    {"echo": text, "input_frame": input_frame, "intent": {"is_research_vault_command": True}, "response_text": vault_command["response_text"], "audio_path": voice_payload.get("audio_path"), "voice_package": voice_payload.get("voice_package"), "tts_provider": voice_payload.get("tts_provider"), "tts_fallback_used": voice_payload.get("tts_fallback_used"), "qwen_tts_endpoint": voice_payload.get("qwen_tts_endpoint"), "cp3_invoked": voice_payload.get("cp3_invoked"), "audio_played": voice_payload.get("audio_played"), "audio_error": voice_payload.get("audio_error"), "research_vault": vault_command},
                    visitor_input=text,
                    intent={"reason": "research_vault"},
                    lead_payload={"source": "research_vault"},
                )
                continue

            skill_result = orb.handle_skill_request(framed_text, input_frame)
            if skill_result:
                voice_payload = orb.build_voice_payload(skill_result["response_text"])
                orb.last_response_text = skill_result["response_text"]
                _emit_with_compliance(
                    "query_result",
                    request_id,
                    {"echo": text, "input_frame": input_frame, "intent": {"is_skill": True}, "response_text": skill_result["response_text"], "audio_path": voice_payload.get("audio_path"), "voice_package": voice_payload.get("voice_package"), "tts_provider": voice_payload.get("tts_provider"), "tts_fallback_used": voice_payload.get("tts_fallback_used"), "qwen_tts_endpoint": voice_payload.get("qwen_tts_endpoint"), "cp3_invoked": voice_payload.get("cp3_invoked"), "audio_played": voice_payload.get("audio_played"), "audio_error": voice_payload.get("audio_error"), "skill": skill_result},
                    visitor_input=text,
                    intent={"reason": "skill"},
                    lead_payload={"source": "skill"},
                )
                continue

            core_result = orb.handle_core_knowledge_request(framed_text)
            if core_result:
                voice_payload = orb.build_voice_payload(core_result["response_text"])
                orb.last_response_text = core_result["response_text"]
                _emit_with_compliance(
                    "query_result",
                    request_id,
                    {"echo": text, "input_frame": input_frame, "intent": {"is_core_knowledge": True}, "response_text": core_result["response_text"], "audio_path": voice_payload.get("audio_path"), "voice_package": voice_payload.get("voice_package"), "tts_provider": voice_payload.get("tts_provider"), "tts_fallback_used": voice_payload.get("tts_fallback_used"), "qwen_tts_endpoint": voice_payload.get("qwen_tts_endpoint"), "cp3_invoked": voice_payload.get("cp3_invoked"), "audio_played": voice_payload.get("audio_played"), "audio_error": voice_payload.get("audio_error"), "core_knowledge": core_result},
                    visitor_input=text,
                    intent={"reason": "core_knowledge"},
                )
                continue

            recall_result = orb.handle_recall_request(framed_text, input_frame)
            if recall_result:
                voice_payload = orb.build_voice_payload(recall_result["response_text"])
                orb.last_response_text = recall_result["response_text"]
                _emit_with_compliance(
                    "query_result",
                    request_id,
                    {"echo": text, "input_frame": input_frame, "intent": {"is_recall": True}, "response_text": recall_result["response_text"], "audio_path": voice_payload.get("audio_path"), "voice_package": voice_payload.get("voice_package"), "tts_provider": voice_payload.get("tts_provider"), "tts_fallback_used": voice_payload.get("tts_fallback_used"), "qwen_tts_endpoint": voice_payload.get("qwen_tts_endpoint"), "cp3_invoked": voice_payload.get("cp3_invoked"), "audio_played": voice_payload.get("audio_played"), "audio_error": voice_payload.get("audio_error"), "recall": recall_result},
                    visitor_input=text,
                    intent={"reason": "recall"},
                )
                continue

            note_result = orb.handle_note_request(framed_text, input_frame, source="text")
            if note_result:
                _emit_with_compliance(
                    "query_result",
                    request_id,
                    {"echo": text, "input_frame": input_frame, "intent": {"is_note": True}, "response_text": note_result["response_text"], "notes": note_result},
                    visitor_input=text,
                    intent={"reason": "note"},
                )
                continue

            intent = orb.detect_research_intent(framed_text, input_frame)
            stimulus = {"type": "text_query", "content": framed_text, "coordinates": [0, 0], "velocity": 0.0, "input_frame": input_frame, "intent": intent}
            result = orb.cognitively_emerge(stimulus)
            research = None
            cali_reasoning = None
            if intent.get("is_research"):
                research = orb.run_research_request(framed_text, intent.get("domains") or [])
                response_text = research.get("response_text") or research.get("voice_response")
            else:
                cali_reasoning = orb.reason_with_cali(framed_text, context={"source": "ipc_query", "stimulus_type": "text_query", "input_frame": input_frame, "semantic": input_frame.get("semantic"), "implied_intent": input_frame.get("implied_intent")})
                response_text = cali_reasoning.get("recommended_response") if cali_reasoning else f"Analyzed: {framed_text}"
            inline_voice = os.getenv("ORB_INLINE_QUERY_VOICE", "0").strip().lower() in {"1", "true", "yes", "on"}
            voice_payload = {}
            if inline_voice:
                voice_payload = orb.build_voice_payload(response_text, "analytical" if research else orb._emotion_from_reasoning(cali_reasoning))
            orb.last_response_text = response_text or ""
            _route_class = "normal" if not research else "tool"
            _cognition_mode = "research" if research else ("governance" if cali_reasoning and cali_reasoning.get("governance_activated") else "deterministic")
            orb.orb_heartbeat.record_route(_route_class)
            orb.orb_heartbeat.set_cognition_mode(_cognition_mode)
            _emit_with_compliance(
                "query_result",
                request_id,
                {"echo": text, "input_frame": input_frame, "intent": intent, "response_text": response_text, "audio_path": voice_payload.get("audio_path"), "voice_package": voice_payload.get("voice_package"), "tts_provider": voice_payload.get("tts_provider"), "tts_fallback_used": voice_payload.get("tts_fallback_used"), "qwen_tts_endpoint": voice_payload.get("qwen_tts_endpoint"), "cp3_invoked": voice_payload.get("cp3_invoked"), "audio_played": voice_payload.get("audio_played"), "audio_error": voice_payload.get("audio_error"), "research": research, "research_synthesis": research.get("research_synthesis") if research else None, "sources": research.get("sources") if research else [], "substrate_record": research.get("substrate_record") if research else None, "cali_reasoning": cali_reasoning, "advisory_verdict": cali_reasoning.get("advisory_verdict") if cali_reasoning else None, "cognitive_result": result.pulse() if hasattr(result, "pulse") else result, "state": {"instance_id": orb.instance_id, "running": orb.running, "controller_status": "active" if orb.controller else "inactive", "listening_enabled": orb.speech_enabled, "auto_listen": orb.auto_listen}, "_route_meta": make_route_meta(provider_selected=orb.instance_id, provider_used="cali_skg" if cali_reasoning else "research_orchestrator", cognition_mode=_cognition_mode, intent=intent.get("reason", "general_query"), route_class=_route_class)},
                visitor_input=text,
                intent=intent,
                lead_payload={"route_class": _route_class},
            )

        elif msg_type == "research":
            query = msg.get("query") or msg.get("text", "")
            domains = msg.get("domains") or []
            research = orb.run_research_request(query, domains)
            voice_payload = orb.build_voice_payload(research.get("response_text", ""))
            orb.last_response_text = research.get("response_text", "") or research.get("voice_response", "")
            _emit_with_compliance(
                "research_result",
                request_id,
                {**research, "voice_package": voice_payload.get("voice_package"), "audio_path": voice_payload.get("audio_path"), "tts_provider": voice_payload.get("tts_provider"), "tts_fallback_used": voice_payload.get("tts_fallback_used"), "qwen_tts_endpoint": voice_payload.get("qwen_tts_endpoint"), "cp3_invoked": voice_payload.get("cp3_invoked"), "audio_played": voice_payload.get("audio_played"), "audio_error": voice_payload.get("audio_error")},
                visitor_input=query,
                intent={"reason": "research"},
                lead_payload={"domains": domains},
            )

        elif msg_type == "speak":
            text = msg.get("text", "")
            emotion = msg.get("emotion", "thoughtful_warm")
            payload = orb.build_voice_payload(text, emotion)
            _emit_with_compliance(
                "speak_result",
                request_id,
                payload,
                visitor_input=text,
                intent={"reason": "speak"},
                orb_profile="desktop_orb",
            )

        elif msg_type == "set_orb_state":
            setting = msg.get("setting")
            value = msg.get("value")
            ok = False
            try:
                ok = orb.set_cali_orb_state(setting, value)
            except Exception as exc:
                print(f"set_orb_state error: {exc}", file=sys.stderr)
            state = {"instance_id": orb.instance_id, "running": orb.running, "controller_status": "active" if orb.controller else "inactive", "listening_enabled": orb.speech_enabled, "auto_listen": orb.auto_listen}
            orb._emit({"type": "orb_state_result", "request_id": request_id, "data": {"ok": ok, "state": state}})


if __name__ == "__main__":
    _main()
