#!/usr/bin/env python3
"""Orb runtime status — normalized status dict builders and helpers."""

import os
from datetime import datetime
from pathlib import Path


def build_runtime_snapshot(
    orb_instance,
    cali_status=None,
    presence_status=None,
    presence_update=None,
    local_llm=None,
    qwen_tts=None,
    cp3_io=None,
    audio_runtime=None,
    controller=None,
):
    """Build the runtime_snapshot dict used by the Electron dock."""
    cali_status = cali_status or {}
    presence_status = presence_status or {}
    presence_update = presence_update or {}
    local_llm = local_llm or {}
    qwen_tts = qwen_tts or {}
    cp3_io = cp3_io or {}
    audio_runtime = audio_runtime or {}

    controller_state = "offline"
    if orb_instance.running:
        controller_state = "ready" if controller else "degraded"

    presence_state = "offline"
    if presence_status.get("running"):
        presence_state = "idle" if (presence_update.get("idle") or presence_status.get("is_idle")) else "active"

    llm_connected = bool(
        local_llm.get("ready")
        or (local_llm.get("endpoint") and local_llm.get("model") and not (local_llm.get("last_runtime") or {}).get("error"))
    )

    realtime_provider = str(
        qwen_tts.get("provider")
        or audio_runtime.get("tts_provider")
        or os.getenv("ORB_REALTIME_TTS_ENGINE")
        or "cosyvoice-stream"
    ).lower()
    qwen_ready = bool(qwen_tts.get("ready"))
    kokoro_ready = bool(
        audio_runtime.get("voice_runtime_ready")
        or audio_runtime.get("voice_adapter_available")
    )
    last_provider = str(audio_runtime.get("tts_provider") or audio_runtime.get("voice_provider") or "").lower()
    if last_provider not in {"qwen", "kokoro", "cosyvoice", "cosyvoice-stream"}:
        last_provider = realtime_provider if qwen_ready else ("kokoro" if kokoro_ready else "none")

    ucm_enabled = os.getenv("ORB_ENABLE_UCM_STATUS_CHECK", "0").strip().lower() in {"1", "true", "yes", "on"}

    return {
        "dock_channel_connected": True,
        "controller_state": controller_state,
        "presence_state": presence_state,
        "listening": bool(orb_instance.speech_enabled),
        "auto_listen": bool(orb_instance.auto_listen),
        "llm_connected": llm_connected,
        "active_llm": str(
            local_llm.get("model")
            or cali_status.get("identity")
            or orb_instance._active_local_model()
            if hasattr(orb_instance, "_active_local_model")
            else "unknown"
        ),
        "governance_wrapper": "on" if local_llm.get("governance_wrapper") else "off",
        "encoder": str(cali_status.get("encoder_backend") or "unknown"),
        "voice_ready": bool(qwen_ready or kokoro_ready),
        "qwen_tts_ready": qwen_ready,
        "realtime_tts_ready": qwen_ready,
        "realtime_tts_endpoint": qwen_tts.get("realtime_endpoint") or qwen_tts.get("endpoint") or os.getenv("ORB_REALTIME_TTS_BASE_URL"),
        "qwen_last_provider": last_provider,
        "qwen_last_error": qwen_tts.get("error") or audio_runtime.get("tts_primary_error") or None,
        "kokoro_ready": kokoro_ready,
        "ucm_enabled": ucm_enabled,
        "ucm_connected": False,
        "ucm_degraded": False,
        "confidence": float(presence_update.get("confidence_state") or 0.0),
        "success_rate": float(cali_status.get("success_rate") or 0.0),
        "anomalies": int(cali_status.get("anomalies") or 0),
        "interactions": int(cali_status.get("interaction_count") or 0),
        "last_error": local_llm.get("error") or qwen_tts.get("error") or None,
        "last_updated": datetime.now().isoformat(),
    }


def build_substrate_status(orb_instance):
    """Build substrate filesystem status."""
    project_root = Path(orb_instance.project_root)
    cali_root = project_root / "CALI_System"
    memory_root = cali_root / "memory"
    voice_cache_root = cali_root / "voice_cache"
    logs_root = project_root / "logs"
    decisions_path = memory_root / "decisions.jsonl"
    short_term_cache_path = memory_root / "short_term_cache.db"

    return {
        "project_root": str(project_root),
        "cali_system_root": str(cali_root),
        "cali_system_exists": cali_root.exists(),
        "memory_root": str(memory_root),
        "memory_exists": memory_root.exists(),
        "notes_root": str(orb_instance.cali_notes.base_path) if hasattr(orb_instance, "cali_notes") else None,
        "notes_exists": orb_instance.cali_notes.base_path.exists() if hasattr(orb_instance, "cali_notes") else False,
        "voice_cache_root": str(voice_cache_root),
        "voice_cache_exists": voice_cache_root.exists(),
        "logs_root": str(logs_root),
        "logs_exists": logs_root.exists(),
        "short_term_cache_path": str(short_term_cache_path),
        "short_term_cache_exists": short_term_cache_path.exists(),
        "decisions_path": str(decisions_path),
        "decisions_exists": decisions_path.exists(),
    }


def build_legacy_acp_io(cp3_io):
    """Build legacy ACP IO compatibility surface."""
    legacy = dict(cp3_io)
    legacy["acp3_root"] = cp3_io.get("cp3_root")
    legacy["acp3_root_exists"] = cp3_io.get("cp3_root_exists")
    return legacy
