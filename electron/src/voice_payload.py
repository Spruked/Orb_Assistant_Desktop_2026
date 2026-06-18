#!/usr/bin/env python3
"""Voice payload — normalized response object builder for Orb voice output."""

import os


def build_voice_payload(text, tts_result=None, voice_package=None, cali=None, orb_state_voice_active=True):
    """Build a normalized voice payload from text + optional TTS result + optional CALI voice package.

    Does NOT perform TTS itself. Does NOT play audio.
    """
    audio_path = None
    tts_provider = "qwen"
    tts_fallback_used = False
    qwen_tts_endpoint = None
    cp3_invoked = False
    audio_error = ""
    audio_url = None

    if isinstance(tts_result, dict):
        audio_path = tts_result.get("audio_path")
        audio_url = tts_result.get("audio_url")
        tts_provider = tts_result.get("tts_provider", "qwen")
        tts_fallback_used = bool(tts_result.get("tts_fallback_used"))
        qwen_tts_endpoint = tts_result.get("qwen_tts_endpoint")
        cp3_invoked = bool(tts_result.get("cp3_invoked"))
        audio_error = tts_result.get("audio_error", "")

    return {
        "text": text,
        "audio_path": audio_path,
        "audio_url": audio_url,
        "voice_package": voice_package,
        "tts_provider": tts_provider,
        "tts_fallback_used": tts_fallback_used,
        "qwen_tts_endpoint": qwen_tts_endpoint,
        "cp3_invoked": cp3_invoked,
        "audio_played": False,
        "audio_error": audio_error,
        "voice": os.getenv("KOKORO_DEFAULT_VOICE", "af_sky"),
    }


def check_voice_display_mismatch(last_response_text, text, emit_fn=None):
    """ORB Standard VI — voice must speak exactly what will be displayed."""
    if last_response_text and text != last_response_text:
        msg = (
            f"⚠️ Voice/display mismatch: voice='{text[:60]}' display='{last_response_text[:60]}'"
        )
        if emit_fn:
            emit_fn({"type": "warning", "data": {"message": msg, "code": "voice_display_mismatch"}})
        return False
    return True
