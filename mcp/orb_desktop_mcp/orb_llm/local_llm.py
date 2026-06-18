"""
ORB Local LLM Client — OPTIONAL articulation layer only.

ARCHITECTURAL RULE:
  ORB cognition (TPC + R-Substrate) is the PRIMARY reasoning layer.
  This LLM client is an OPTIONAL fallback for when TPC confidence < 0.30
  AND the user has explicitly set use_llm=True.

  The LLM is an articulation layer only.
  It must NEVER receive governance doctrine.
  It must NEVER be the primary decision maker.
  All LLM output is re-routed through TPC for validation before execution.

Supported backends (in priority order):
  1. Ollama (local, preferred)
  2. LM Studio (local)
  3. Any OpenAI-compatible local endpoint
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass
class LLMResult:
    success: bool
    text: str = ""
    error: str = ""
    backend: str = ""
    tokens_used: int = 0


class LocalLLMClient:
    """
    Detects and wraps a locally running LLM.
    Returns LLMResult — callers must check result.success.
    """

    # Endpoints to probe, in order
    PROBE_ENDPOINTS = [
        ("ollama",    "http://localhost:11434"),
        ("lmstudio",  "http://localhost:1234"),
        ("localai",   "http://localhost:8080"),
        ("textgen",   "http://localhost:5000"),
    ]

    def __init__(self):
        self._backend:  Optional[str] = None
        self._base_url: Optional[str] = None
        self._model:    Optional[str] = None
        self._ready:    bool          = False
        self._probe()

    def _probe(self) -> None:
        """Probe each known endpoint. First success wins."""
        try:
            import requests
            for name, url in self.PROBE_ENDPOINTS:
                try:
                    r = requests.get(f"{url}/", timeout=1.0)
                    if r.status_code < 500:
                        self._backend  = name
                        self._base_url = url
                        self._ready    = True
                        self._model    = self._detect_model(name, url)
                        return
                except Exception:
                    continue
        except ImportError:
            pass  # requests not installed — stay unavailable

    def _detect_model(self, backend: str, url: str) -> Optional[str]:
        """Try to detect the loaded model name."""
        import requests
        try:
            if backend == "ollama":
                r = requests.get(f"{url}/api/tags", timeout=2.0)
                if r.status_code == 200:
                    models = r.json().get("models", [])
                    if models:
                        return models[0].get("name", "unknown")
            elif backend in ("lmstudio", "localai", "textgen"):
                r = requests.get(f"{url}/v1/models", timeout=2.0)
                if r.status_code == 200:
                    data = r.json()
                    items = data.get("data", [])
                    if items:
                        return items[0].get("id", "unknown")
        except Exception:
            pass
        return "unknown"

    @property
    def available(self) -> bool:
        return self._ready

    @property
    def backend(self) -> Optional[str]:
        return self._backend

    @property
    def model(self) -> Optional[str]:
        return self._model

    def generate(self, prompt: str, max_tokens: int = 256, temperature: float = 0.1) -> LLMResult:
        """
        Generate a completion from the local LLM.
        Temperature defaults low (0.1) — we want deterministic articulation.
        """
        if not self._ready:
            return LLMResult(
                success=False,
                error="No local LLM available",
                backend="none",
            )

        try:
            if self._backend == "ollama":
                return self._call_ollama(prompt, max_tokens, temperature)
            else:
                return self._call_openai_compat(prompt, max_tokens, temperature)
        except Exception as e:
            return LLMResult(success=False, error=str(e), backend=self._backend or "unknown")

    def _call_ollama(self, prompt: str, max_tokens: int, temperature: float) -> LLMResult:
        import requests, json
        payload = {
            "model":  self._model or "llama3",
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
            }
        }
        r = requests.post(
            f"{self._base_url}/api/generate",
            json=payload,
            timeout=30.0
        )
        r.raise_for_status()
        data = r.json()
        return LLMResult(
            success=True,
            text=data.get("response", "").strip(),
            backend="ollama",
            tokens_used=data.get("eval_count", 0),
        )

    def _call_openai_compat(self, prompt: str, max_tokens: int, temperature: float) -> LLMResult:
        import requests
        payload = {
            "model":       self._model or "local-model",
            "messages":    [{"role": "user", "content": prompt}],
            "max_tokens":  max_tokens,
            "temperature": temperature,
        }
        r = requests.post(
            f"{self._base_url}/v1/chat/completions",
            json=payload,
            timeout=30.0
        )
        r.raise_for_status()
        data    = r.json()
        choices = data.get("choices", [])
        text    = choices[0]["message"]["content"].strip() if choices else ""
        return LLMResult(
            success=True,
            text=text,
            backend=self._backend or "openai-compat",
            tokens_used=data.get("usage", {}).get("completion_tokens", 0),
        )

    def status(self) -> dict:
        return {
            "available": self._ready,
            "backend":   self._backend,
            "model":     self._model,
            "base_url":  self._base_url,
        }
