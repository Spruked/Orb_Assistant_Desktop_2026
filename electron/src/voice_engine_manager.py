#!/usr/bin/env python3
"""
Voice engine abstraction layer for multiple TTS providers.
Supports WSL Kokoro, ACP 3.0, and fallbacks.
"""

import json
import logging
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger("VoiceEngine")


class EngineStatus(Enum):
    """Voice engine status states."""
    UNKNOWN = "unknown"
    LOADING = "loading"
    ONLINE = "online"
    ERROR = "error"
    UNAVAILABLE = "unavailable"


@dataclass
class HealthStatus:
    """Health status of a voice engine."""
    status: EngineStatus
    provider: str
    message: str = ""
    latency_ms: float = 0.0
    sample_rate: int = 24000
    extra: Dict = None

    def to_dict(self):
        return {
            "status": self.status.value,
            "provider": self.provider,
            "message": self.message,
            "latency_ms": self.latency_ms,
            "sample_rate": self.sample_rate,
            "extra": self.extra or {}
        }


class VoiceEngine(ABC):
    """Abstract base class for voice/TTS engines."""

    def __init__(self, name: str):
        self.name = name
        self.status = EngineStatus.UNKNOWN

    @abstractmethod
    def initialize(self) -> bool:
        """Initialize the engine. Return True if successful."""
        pass

    @abstractmethod
    def synthesize(self, text: str, voice_id: str = "af_sky", 
                   emotion: str = "neutral") -> Optional[bytes]:
        """Synthesize speech to audio bytes. Return None on failure."""
        pass

    @abstractmethod
    def get_health_status(self) -> HealthStatus:
        """Get engine health and status."""
        pass

    def is_available(self) -> bool:
        """Check if engine is available and online."""
        return self.status == EngineStatus.ONLINE


class KokoroWSLEngine(VoiceEngine):
    """Kokoro TTS via WSL HTTP endpoint."""

    def __init__(self, endpoint: str = None, timeout_ms: int = 30000):
        super().__init__("kokoro_wsl")
        self.endpoint = endpoint or os.getenv("KOKORO_WSL_ENDPOINT", "http://127.0.0.1:8888")
        self.timeout_seconds = timeout_ms / 1000.0
        self.last_latency = 0.0

    def initialize(self) -> bool:
        """Test connection to WSL Kokoro endpoint."""
        self.status = EngineStatus.LOADING
        try:
            # Test health endpoint
            request = urllib.request.Request(
                f"{self.endpoint}/health",
                method="GET"
            )
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
                self.status = EngineStatus.ONLINE
                logger.info(f"✓ Kokoro WSL engine initialized: {self.endpoint}")
                return True
        except Exception as e:
            self.status = EngineStatus.ERROR
            logger.warning(f"⚠ Kokoro WSL engine unavailable: {e}")
            return False

    def synthesize(self, text: str, voice_id: str = "af_sky", 
                   emotion: str = "neutral") -> Optional[bytes]:
        """Synthesize text to speech via Kokoro WSL."""
        if not self.is_available():
            return None

        try:
            request_body = {
                "text": text,
                "voice": voice_id,
                "emotion": emotion,
                "lang": "en"
            }
            
            request = urllib.request.Request(
                f"{self.endpoint}/synthesize",
                data=json.dumps(request_body).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            
            start = time.time()
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                self.last_latency = (time.time() - start) * 1000
                return response.read()
        except Exception as e:
            logger.error(f"Kokoro WSL synthesis error: {e}")
            return None

    def get_health_status(self) -> HealthStatus:
        """Check Kokoro WSL health."""
        return HealthStatus(
            status=self.status,
            provider=self.name,
            message=f"Endpoint: {self.endpoint}",
            latency_ms=self.last_latency
        )


class ACP3Engine(VoiceEngine):
    """ACP 3.0 (Cochlear Processor) voice engine."""

    def __init__(self):
        super().__init__("acp3_kokoro")
        self.kokoro_baseline = None
        self.provider_info = None

    def initialize(self) -> bool:
        """Initialize ACP 3.0 KokoroBaseline."""
        self.status = EngineStatus.LOADING
        try:
            # Dynamically import ACP 3.0
            from orb_acp3_adapter import KokoroBaseline
            self.kokoro_baseline = KokoroBaseline()
            
            # Verify it has the required interface
            if not hasattr(self.kokoro_baseline, 'get_health_status'):
                raise AttributeError("KokoroBaseline missing get_health_status method")
            
            health = self.kokoro_baseline.get_health_status()
            self.provider_info = health.get('onnx_provider', 'unknown')
            self.status = EngineStatus.ONLINE
            logger.info(f"✓ ACP 3.0 engine initialized (provider: {self.provider_info})")
            return True
        except ImportError as e:
            self.status = EngineStatus.UNAVAILABLE
            logger.debug(f"ACP 3.0 not available: {e}")
            return False
        except Exception as e:
            self.status = EngineStatus.ERROR
            logger.warning(f"⚠ ACP 3.0 engine init failed: {e}")
            return False

    def synthesize(self, text: str, voice_id: str = "af_sky", 
                   emotion: str = "neutral") -> Optional[bytes]:
        """Synthesize using ACP 3.0 KokoroBaseline."""
        if not self.is_available() or not self.kokoro_baseline:
            return None

        try:
            # ACP 3.0 interface - may vary, adjust as needed
            result = self.kokoro_baseline.synthesize(
                text=text,
                voice=voice_id,
                emotion=emotion
            )
            # Assume result is bytes or has 'audio' key
            if isinstance(result, bytes):
                return result
            elif isinstance(result, dict) and 'audio' in result:
                return result['audio']
            else:
                return result
        except Exception as e:
            logger.error(f"ACP 3.0 synthesis error: {e}")
            return None

    def get_health_status(self) -> HealthStatus:
        """Check ACP 3.0 health."""
        try:
            if self.kokoro_baseline and hasattr(self.kokoro_baseline, 'get_health_status'):
                health_dict = self.kokoro_baseline.get_health_status()
                return HealthStatus(
                    status=self.status,
                    provider=self.name,
                    message=f"Provider: {self.provider_info}",
                    extra=health_dict
                )
        except Exception as e:
            logger.warning(f"ACP 3.0 health check error: {e}")
        
        return HealthStatus(
            status=self.status,
            provider=self.name,
            message=f"Provider: {self.provider_info}" if self.provider_info else "Unknown"
        )


class NullEngine(VoiceEngine):
    """Fallback null engine - returns empty bytes."""

    def __init__(self):
        super().__init__("null")
        self.status = EngineStatus.ONLINE

    def initialize(self) -> bool:
        return True

    def synthesize(self, text: str, voice_id: str = "af_sky", 
                   emotion: str = "neutral") -> Optional[bytes]:
        """Return empty bytes as fallback."""
        return b""

    def get_health_status(self) -> HealthStatus:
        return HealthStatus(
            status=EngineStatus.ONLINE,
            provider=self.name,
            message="Fallback null engine (no audio)"
        )


class VoiceEngineManager:
    """Manages multiple voice engines with fallback chain."""

    def __init__(self, fallback_chain: list = None):
        """
        Initialize voice engine manager.
        
        Args:
            fallback_chain: List of engine names to try in order.
                           Default: ["kokoro_wsl", "acp3", "null"]
        """
        self.engines: Dict[str, VoiceEngine] = {}
        self.fallback_chain = fallback_chain or ["kokoro_wsl", "acp3", "null"]
        self.active_engine: Optional[VoiceEngine] = None
        
        # Initialize all known engines
        self._init_engines()

    def _init_engines(self):
        """Initialize all available engines."""
        logger.info("Initializing voice engines...")
        
        # Kokoro WSL
        kokoro_wsl = KokoroWSLEngine()
        self.engines["kokoro_wsl"] = kokoro_wsl
        if kokoro_wsl.initialize():
            if not self.active_engine:
                self.active_engine = kokoro_wsl
        
        # ACP 3.0
        acp3 = ACP3Engine()
        self.engines["acp3"] = acp3
        if acp3.initialize():
            if not self.active_engine:
                self.active_engine = acp3
        
        # Null (always available)
        null = NullEngine()
        self.engines["null"] = null
        if null.initialize():
            if not self.active_engine:
                self.active_engine = null
        
        # Log status
        active_name = self.active_engine.name if self.active_engine else "none"
        logger.info(f"✓ Voice engine manager ready (active: {active_name})")

    def synthesize(self, text: str, voice_id: str = "af_sky", 
                   emotion: str = "neutral", use_fallback: bool = True) -> Optional[bytes]:
        """
        Synthesize text to speech using active engine or fallback chain.
        
        Args:
            text: Text to synthesize
            voice_id: Voice identifier
            emotion: Emotional tone
            use_fallback: Try fallback engines if active fails
            
        Returns:
            Audio bytes or None
        """
        if not text or not text.strip():
            return None
        
        # Try active engine first
        if self.active_engine:
            audio = self.active_engine.synthesize(text, voice_id, emotion)
            if audio is not None:
                return audio
            logger.warning(f"Active engine {self.active_engine.name} failed, trying fallbacks...")
        
        # Try fallback chain
        if use_fallback:
            for engine_name in self.fallback_chain:
                engine = self.engines.get(engine_name)
                if engine and engine.is_available():
                    logger.debug(f"Trying fallback engine: {engine_name}")
                    audio = engine.synthesize(text, voice_id, emotion)
                    if audio is not None:
                        self.active_engine = engine  # Update active
                        logger.info(f"✓ Fallback succeeded with {engine_name}")
                        return audio
        
        logger.error("All voice engines failed")
        return None

    def get_status(self) -> Dict:
        """Get status of all engines."""
        return {
            "active_engine": self.active_engine.name if self.active_engine else None,
            "fallback_chain": self.fallback_chain,
            "engines": {
                name: engine.get_health_status().to_dict()
                for name, engine in self.engines.items()
            }
        }

    def set_active_engine(self, name: str) -> bool:
        """Manually set active engine."""
        engine = self.engines.get(name)
        if engine and engine.is_available():
            self.active_engine = engine
            logger.info(f"✓ Active engine set to: {name}")
            return True
        logger.warning(f"Cannot set active engine to {name}")
        return False


# Global instance (singleton-ish)
_manager_instance: Optional[VoiceEngineManager] = None


def get_voice_manager() -> VoiceEngineManager:
    """Get or create global voice manager instance."""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = VoiceEngineManager()
    return _manager_instance


if __name__ == "__main__":
    # Test script
    logging.basicConfig(level=logging.DEBUG)
    
    manager = get_voice_manager()
    print("\n=== Voice Engine Manager Status ===")
    print(json.dumps(manager.get_status(), indent=2))
    
    # Test synthesis
    test_text = "Hello, this is a test of the voice engine."
    print(f"\n=== Testing synthesis: '{test_text}' ===")
    audio = manager.synthesize(test_text)
    if audio:
        print(f"✓ Synthesis successful ({len(audio)} bytes)")
    else:
        print("✗ Synthesis failed")
