from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict

from orb_desktop.desktop_orchestrator import ORBResult


def _qwen_code_config() -> Dict[str, Any]:
    root = Path(os.getenv(
        "ORB_QWEN_CODE_ROOT",
        r"R:\Services\qwen-code-main\qwen-code-main",
    ))
    entrypoint = Path(os.getenv(
        "ORB_QWEN_CODE_ENTRYPOINT",
        str(root / "packages" / "cli" / "dist" / "index.js"),
    ))
    command = os.getenv("ORB_QWEN_CODE_COMMAND", "node").strip() or "node"
    try:
        timeout_sec = max(5.0, float(os.getenv("ORB_QWEN_CODE_TIMEOUT_SEC", "90")))
    except ValueError:
        timeout_sec = 90.0
    return {
        "root": str(root),
        "entrypoint": str(entrypoint),
        "command": command,
        "auth_type": os.getenv("ORB_QWEN_CODE_AUTH_TYPE", "openai").strip() or "openai",
        "base_url": os.getenv("ORB_QWEN_CODE_BASE_URL", os.getenv("OPENAI_BASE_URL", "http://127.0.0.1:40343/v1")).strip(),
        "model": os.getenv("ORB_QWEN_CODE_MODEL", os.getenv("ORB_LOCAL_LLM_MODEL", "Qwen/Qwen2.5-1.5B-Instruct-GGUF:Q4_K_M")).strip(),
        "api_key": os.getenv("ORB_QWEN_CODE_API_KEY", os.getenv("OPENAI_API_KEY", "local")).strip() or "local",
        "timeout_sec": timeout_sec,
        "ready": root.exists() and entrypoint.exists(),
    }


def qwen_code_status() -> ORBResult:
    config = _qwen_code_config()
    if not config["ready"]:
        return ORBResult.fail(json.dumps(config, separators=(",", ":")))
    started = time.perf_counter()
    proc = subprocess.run(
        [config["command"], config["entrypoint"], "--version"],
        cwd=config["root"],
        capture_output=True,
        text=True,
        timeout=min(20.0, float(config["timeout_sec"])),
    )
    payload = {
        **config,
        "api_key": "set" if config.get("api_key") else "",
        "returncode": proc.returncode,
        "version": (proc.stdout or proc.stderr or "").strip(),
        "latency_ms": round((time.perf_counter() - started) * 1000),
    }
    if proc.returncode != 0:
        payload["stderr"] = (proc.stderr or "").strip()
        return ORBResult.fail(json.dumps(payload, separators=(",", ":")))
    return ORBResult.ok(json.dumps(payload, separators=(",", ":")))


def run_qwen_code_prompt(prompt: str, output_format: str = "text", timeout_sec: float | None = None) -> ORBResult:
    config = _qwen_code_config()
    if not config["ready"]:
        return ORBResult.fail(json.dumps(config, separators=(",", ":")))
    prompt = str(prompt or "").strip()
    if not prompt:
        return ORBResult.fail("missing prompt")
    output_format = output_format if output_format in {"text", "json", "stream-json"} else "text"
    timeout = float(timeout_sec or config["timeout_sec"])
    started = time.perf_counter()
    env = dict(os.environ)
    env["OPENAI_BASE_URL"] = config["base_url"]
    env["OPENAI_API_KEY"] = config["api_key"]
    env["OPENAI_MODEL"] = config["model"]
    proc = subprocess.run(
        [
            config["command"],
            config["entrypoint"],
            "--auth-type",
            config["auth_type"],
            "--model",
            config["model"],
            "--prompt",
            prompt,
            "--output-format",
            output_format,
        ],
        cwd=config["root"],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    payload = {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "").strip(),
        "stderr": (proc.stderr or "").strip(),
        "latency_ms": round((time.perf_counter() - started) * 1000),
        "root": config["root"],
        "entrypoint": config["entrypoint"],
        "auth_type": config["auth_type"],
        "base_url": config["base_url"],
        "model": config["model"],
        "output_format": output_format,
    }
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return ORBResult.ok(text) if proc.returncode == 0 else ORBResult.fail(text)
