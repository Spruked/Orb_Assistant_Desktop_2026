#!/usr/bin/env python3
"""
LLM client abstraction for Ollama with Qwen 2.5 3B support.
Handles model validation, streaming, and fallbacks.
"""

import json
import logging
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger("LLMClient")


class LLMProvider(Enum):
    """Supported LLM providers."""
    OLLAMA = "ollama"
    UNKNOWN = "unknown"


@dataclass
class LLMConfig:
    """LLM configuration."""
    provider: LLMProvider = LLMProvider.OLLAMA
    endpoint: str = "http://127.0.0.1:11434"
    model: str = "qwen2.5:3b"
    timeout_seconds: float = 120.0
    streaming_enabled: bool = True
    validate_model_on_startup: bool = True
    keep_alive: str = "15m"
    gpu_layers: Optional[int] = None
    temperature: float = 0.7
    top_p: float = 0.9
    
    @classmethod
    def from_env(cls) -> "LLMConfig":
        """Create config from environment variables."""
        return cls(
            endpoint=os.getenv("ORB_LOCAL_LLM_ENDPOINT", "http://127.0.0.1:11434"),
            model=os.getenv("ORB_LOCAL_LLM_MODEL", "qwen2.5:3b"),
            timeout_seconds=float(os.getenv("ORB_LLM_TIMEOUT_SECONDS", "120")),
            streaming_enabled=os.getenv("ORB_LLM_STREAMING", "1").lower() in {"1", "true", "yes"},
            validate_model_on_startup=os.getenv("ORB_LLM_VALIDATE_ON_STARTUP", "1").lower() in {"1", "true", "yes"},
            keep_alive=os.getenv("CALI_OLLAMA_KEEP_ALIVE", "15m"),
            gpu_layers=int(os.getenv("CALI_OLLAMA_NUM_GPU", "0")) if os.getenv("CALI_OLLAMA_NUM_GPU") else None,
            temperature=float(os.getenv("ORB_LLM_TEMPERATURE", "0.7")),
            top_p=float(os.getenv("ORB_LLM_TOP_P", "0.9"))
        )


@dataclass
class LLMResponse:
    """LLM response with metadata."""
    text: str
    model: str
    provider: str
    latency_ms: float
    success: bool
    streaming: bool = False
    error: Optional[str] = None
    metadata: Dict = field(default_factory=dict)
    
    def to_dict(self):
        return {
            "text": self.text,
            "model": self.model,
            "provider": self.provider,
            "latency_ms": self.latency_ms,
            "success": self.success,
            "streaming": self.streaming,
            "error": self.error,
            "metadata": self.metadata
        }


class OllamaClient:
    """Ollama client for local LLM queries."""

    def __init__(self, config: LLMConfig = None):
        """Initialize Ollama client."""
        self.config = config or LLMConfig.from_env()
        self.available_models: List[str] = []
        self.model_available = False
        self.last_error: Optional[str] = None
        self.last_query_time: float = 0.0
        
        # Initialize and validate
        self._initialize()

    def _initialize(self):
        """Initialize client and validate model availability."""
        logger.info(f"Initializing Ollama client: {self.config.endpoint}")
        
        # Check connection
        if not self._check_health():
            logger.error("Ollama server not responding")
            return
        
        # List available models
        self.available_models = self._list_models()
        logger.info(f"✓ Ollama connected ({len(self.available_models)} models available)")
        
        # Validate configured model
        if self.config.validate_model_on_startup:
            self.model_available = self._validate_model()
            if not self.model_available:
                logger.warning(f"Model '{self.config.model}' not found in Ollama")
                # Try to find a fallback
                if "qwen" in [m.lower() for m in self.available_models]:
                    logger.info("Found Qwen model, using as fallback")
                    for m in self.available_models:
                        if "qwen" in m.lower():
                            self.config.model = m
                            self.model_available = True
                            logger.info(f"✓ Using fallback model: {m}")
                            break
        else:
            self.model_available = True

    def _check_health(self) -> bool:
        """Check if Ollama server is healthy."""
        try:
            request = urllib.request.Request(
                f"{self.config.endpoint}/api/tags",
                method="GET",
                headers={"Accept": "application/json"}
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                if response.status == 200:
                    logger.debug("✓ Ollama server health check passed")
                    return True
        except Exception as e:
            self.last_error = str(e)
            logger.warning(f"Ollama health check failed: {e}")
        return False

    def _list_models(self) -> List[str]:
        """List available models from Ollama."""
        try:
            request = urllib.request.Request(
                f"{self.config.endpoint}/api/tags",
                method="GET",
                headers={"Accept": "application/json"}
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))
                models = [m["name"] for m in data.get("models", [])]
                return models
        except Exception as e:
            logger.warning(f"Failed to list models: {e}")
            return []

    def _validate_model(self) -> bool:
        """Check if configured model is available."""
        if not self.available_models:
            return False
        
        # Exact match
        if self.config.model in self.available_models:
            return True
        
        # Partial match (e.g., "qwen2.5:3b" matches "qwen2.5:3b-instruct")
        for model in self.available_models:
            if self.config.model.lower() in model.lower():
                return True
        
        return False

    def query(self, prompt: str, stream: bool = None, 
              temperature: float = None) -> LLMResponse:
        """
        Query the LLM.
        
        Args:
            prompt: Input prompt
            stream: Whether to stream response (None = use config default)
            temperature: Sampling temperature (None = use config default)
            
        Returns:
            LLMResponse object
        """
        if not prompt or not prompt.strip():
            return LLMResponse(
                text="",
                model=self.config.model,
                provider="ollama",
                latency_ms=0,
                success=False,
                error="Empty prompt"
            )
        
        if not self.model_available:
            return LLMResponse(
                text="",
                model=self.config.model,
                provider="ollama",
                latency_ms=0,
                success=False,
                error=f"Model '{self.config.model}' not available. Available: {self.available_models}"
            )
        
        stream = stream if stream is not None else self.config.streaming_enabled
        temperature = temperature if temperature is not None else self.config.temperature
        
        request_body = {
            "model": self.config.model,
            "prompt": prompt,
            "stream": stream,
            "keep_alive": self.config.keep_alive,
            "temperature": temperature,
            "top_p": self.config.top_p
        }
        
        if self.config.gpu_layers is not None:
            request_body["options"] = {"num_gpu": self.config.gpu_layers}
        
        started = time.time()
        try:
            request = urllib.request.Request(
                f"{self.config.endpoint}/api/generate",
                data=json.dumps(request_body).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                if stream:
                    # Handle streaming response
                    response_text = ""
                    for line in response:
                        try:
                            chunk = json.loads(line.decode("utf-8"))
                            response_text += chunk.get("response", "")
                            if chunk.get("done"):
                                break
                        except json.JSONDecodeError:
                            continue
                else:
                    # Non-streaming response
                    data = json.loads(response.read().decode("utf-8"))
                    response_text = data.get("response", "").strip()
            
            latency_ms = (time.time() - started) * 1000
            self.last_query_time = latency_ms
            self.last_error = None
            
            logger.debug(f"✓ LLM query successful ({latency_ms:.0f}ms)")
            
            return LLMResponse(
                text=response_text,
                model=self.config.model,
                provider="ollama",
                latency_ms=latency_ms,
                success=True,
                streaming=stream,
                metadata={
                    "prompt_length": len(prompt),
                    "response_length": len(response_text),
                    "temperature": temperature
                }
            )
            
        except urllib.error.URLError as e:
            latency_ms = (time.time() - started) * 1000
            error_msg = f"Connection failed: {e}"
            self.last_error = error_msg
            logger.error(f"✗ LLM query failed: {error_msg}")
            
            return LLMResponse(
                text="",
                model=self.config.model,
                provider="ollama",
                latency_ms=latency_ms,
                success=False,
                error=error_msg
            )
            
        except urllib.error.HTTPError as e:
            latency_ms = (time.time() - started) * 1000
            error_msg = f"HTTP {e.code}: {e.reason}"
            self.last_error = error_msg
            logger.error(f"✗ LLM query failed: {error_msg}")
            
            return LLMResponse(
                text="",
                model=self.config.model,
                provider="ollama",
                latency_ms=latency_ms,
                success=False,
                error=error_msg
            )
            
        except Exception as e:
            latency_ms = (time.time() - started) * 1000
            error_msg = f"Query error: {str(e)}"
            self.last_error = error_msg
            logger.error(f"✗ LLM query failed: {error_msg}")
            
            return LLMResponse(
                text="",
                model=self.config.model,
                provider="ollama",
                latency_ms=latency_ms,
                success=False,
                error=error_msg
            )

    def get_status(self) -> Dict:
        """Get client status."""
        return {
            "endpoint": self.config.endpoint,
            "model": self.config.model,
            "provider": self.config.provider.value,
            "available": self.model_available,
            "available_models": self.available_models,
            "last_error": self.last_error,
            "last_query_latency_ms": self.last_query_time,
            "config": {
                "timeout_seconds": self.config.timeout_seconds,
                "streaming_enabled": self.config.streaming_enabled,
                "temperature": self.config.temperature,
                "top_p": self.config.top_p
            }
        }


# Global instance
_client_instance: Optional[OllamaClient] = None


def get_llm_client(config: LLMConfig = None) -> OllamaClient:
    """Get or create global LLM client instance."""
    global _client_instance
    if _client_instance is None:
        _client_instance = OllamaClient(config or LLMConfig.from_env())
    return _client_instance


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    # Initialize client
    client = get_llm_client()
    
    # Show status
    print("\n=== LLM Client Status ===")
    status = client.get_status()
    for key, value in status.items():
        if key != "config":
            print(f"{key}: {value}")
    print("\nConfig:")
    for key, value in status["config"].items():
        print(f"  {key}: {value}")
    
    # Test query
    if client.model_available:
        print("\n=== Testing LLM Query ===")
        prompt = "What is 2 + 2?"
        response = client.query(prompt, stream=False)
        print(f"Prompt: {prompt}")
        print(f"Response: {response.text}")
        print(f"Latency: {response.latency_ms:.0f}ms")
        print(f"Success: {response.success}")
        if response.error:
            print(f"Error: {response.error}")
    else:
        print("\n⚠ LLM model not available - cannot test query")
