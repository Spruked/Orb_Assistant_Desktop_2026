#!/usr/bin/env python3
"""LLM client — Ollama/Qwen local LLM calls only. Not the brain."""

import json
import os
import sys
import time
import urllib.request
from pathlib import Path


def _active_local_endpoint(cali=None):
    default_local_endpoint = os.getenv("ORB_LOCAL_LLM_ENDPOINT", "http://wsl.localhost:11434")
    if cali:
        endpoint = cali.orb_state.get("llm_local_endpoint") or default_local_endpoint
    else:
        endpoint = default_local_endpoint
    endpoint = str(endpoint or "").rstrip("/")
    if os.name == "nt" and "wsl.localhost" in endpoint:
        endpoint = endpoint.replace("wsl.localhost", "127.0.0.1")
    for suffix in ("/api/generate", "/api/tags"):
        if endpoint.endswith(suffix):
            endpoint = endpoint[: -len(suffix)].rstrip("/")
    return endpoint


def _active_local_model(cali=None):
    if cali:
        return cali.orb_state.get("llm_local_model") or os.getenv("ORB_LOCAL_LLM_MODEL", "llama3.2:1b")
    return os.getenv("ORB_LOCAL_LLM_MODEL", "llama3.2:1b")


def _ollama_gpu_options():
    options = {}
    raw_num_gpu = os.getenv("CALI_OLLAMA_NUM_GPU") or os.getenv("OLLAMA_NUM_GPU")
    if raw_num_gpu:
        try:
            options["num_gpu"] = int(raw_num_gpu)
        except ValueError:
            pass
    return options


def _probe_local_llm_health(endpoint=None, model=None):
    endpoint = (endpoint or _active_local_endpoint()).rstrip("/")
    model = str(model or _active_local_model()).strip() or "llama3.2:1b"
    if not endpoint:
        return {
            "ready": False,
            "connected": False,
            "endpoint": "",
            "model": model,
            "status_code": 0,
            "available_models": [],
            "error": "missing_endpoint",
        }
    target = f"{endpoint}/api/tags"
    req = urllib.request.Request(target, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=2.0) as res:
            status_code = int(getattr(res, "status", 0) or 0)
            if 200 <= status_code < 300:
                payload = json.loads(res.read().decode("utf-8", errors="replace") or "{}")
                models = payload.get("models") if isinstance(payload, dict) else []
                model_names = []
                if isinstance(models, list):
                    model_names = [
                        str(item.get("name") or item.get("model") or "").strip()
                        for item in models
                        if isinstance(item, dict)
                    ]
                    model_names = [name for name in model_names if name]
                connected = model in model_names
                error = "" if connected else f"model_not_found:{model}"
                return {
                    "ready": connected,
                    "connected": connected,
                    "endpoint": endpoint,
                    "model": model,
                    "status_code": status_code,
                    "available_models": model_names,
                    "error": error,
                }
            return {
                "ready": False,
                "connected": False,
                "endpoint": endpoint,
                "model": model,
                "status_code": status_code,
                "available_models": [],
                "error": f"http_{status_code}",
            }
    except Exception as exc:
        return {
            "ready": False,
            "connected": False,
            "endpoint": endpoint,
            "model": model,
            "status_code": 0,
            "available_models": [],
            "error": str(exc),
        }


def query_local_llm(text, endpoint=None, model=None, cali=None):
    """Query local Ollama first, then fall back to the governed articulation wrapper."""
    endpoint = (endpoint or _active_local_endpoint(cali=cali)).rstrip("/")
    model = model or _active_local_model(cali=cali)
    request_body = {
        "model": model,
        "prompt": text,
        "stream": False,
        "keep_alive": os.getenv("CALI_OLLAMA_KEEP_ALIVE", os.getenv("OLLAMA_KEEP_ALIVE", "15m")),
        "options": _ollama_gpu_options(),
    }
    started = time.time()
    last_llm_runtime = {}
    try:
        request = urllib.request.Request(
            f"{endpoint}/api/generate",
            data=json.dumps(request_body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
        answer = str(payload.get("response") or "").strip()
        last_llm_runtime = {
            "provider": "ollama",
            "endpoint": endpoint,
            "model": model,
            "requested_gpu_layers": request_body["options"].get("num_gpu"),
            "latency_ms": round((time.time() - started) * 1000),
            "done": bool(payload.get("done")),
        }
        if answer:
            return {
                "recommended_response": answer,
                "source": "ollama_local",
                "model": model,
                "llm_runtime": dict(last_llm_runtime),
                "advisory_verdict": {"confidence": 0.78, "tension_detected": False},
            }
    except Exception as e:
        last_llm_runtime = {
            "provider": "ollama",
            "endpoint": endpoint,
            "model": model,
            "error": str(e),
        }

    try:
        governance_path = Path("R:/substrate/governance")
        if not governance_path.exists():
            governance_path = Path("/mnt/r/substrate/governance")
        governance_path_text = str(governance_path)
        if governance_path_text not in sys.path:
            sys.path.insert(0, governance_path_text)

        loader = sys.modules.get("loader")
        if loader is None:
            import loader

        answer = loader.run("orb_articulation", text).strip()
        if answer:
            return {
                "recommended_response": answer,
                "source": "governed_local_llm",
                "model": model,
                "llm_runtime": dict(last_llm_runtime),
                "advisory_verdict": {"confidence": 0.75, "tension_detected": False},
            }
    except Exception as e:
        pass
    return None


class LLMClient:
    """Local LLM client wrapper with health probing."""

    def __init__(self, cali=None):
        self.cali = cali
        self.last_llm_runtime = {}

    def get_endpoint(self):
        return _active_local_endpoint(cali=self.cali)

    def get_model(self):
        return _active_local_model(cali=self.cali)

    def get_gpu_options(self):
        return _ollama_gpu_options()

    def health_check(self):
        return _probe_local_llm_health(endpoint=self.get_endpoint(), model=self.get_model())

    def query(self, text):
        result = query_local_llm(text, cali=self.cali)
        if result and result.get("llm_runtime"):
            self.last_llm_runtime = result["llm_runtime"]
        return result
