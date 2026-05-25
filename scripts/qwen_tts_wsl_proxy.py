#!/usr/bin/env python3
"""WSL-local proxy for the Windows Qwen TTS bridge.

Qwen TTS runs on Windows Python 3.12. Some WSL/Docker ORB services cannot reach
the Windows listener directly because the Windows firewall blocks vEthernet
inbound traffic. This proxy stays inside WSL on 127.0.0.1:8021 and invokes the
Windows bridge through powershell.exe.
"""

from __future__ import annotations

import json
import os
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


LISTEN_HOST = os.getenv("ORB_QWEN_TTS_WSL_PROXY_HOST", "127.0.0.1")
LISTEN_PORT = int(os.getenv("ORB_QWEN_TTS_WSL_PROXY_PORT", "8021"))
WINDOWS_BRIDGE = os.getenv("ORB_QWEN_TTS_WINDOWS_BRIDGE", "http://127.0.0.1:8020").rstrip("/")


def _powershell_json(method: str, route: str, body: str | None = None, timeout: int = 180) -> tuple[int, dict[str, Any]]:
    target = f"{WINDOWS_BRIDGE}/{route.lstrip('/')}"
    if method == "GET":
        command = (
            f"$r=Invoke-RestMethod -Uri '{target}' -Method Get -TimeoutSec 10; "
            "$r | ConvertTo-Json -Depth 12 -Compress"
        )
        input_text = None
    else:
        command = (
            "$body=[Console]::In.ReadToEnd(); "
            f"$r=Invoke-RestMethod -Uri '{target}' -Method Post "
            "-ContentType 'application/json' -Body $body -TimeoutSec 180; "
            "$r | ConvertTo-Json -Depth 12 -Compress"
        )
        input_text = body or "{}"

    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        input=input_text,
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        return 502, {"status": "error", "error": (proc.stderr or proc.stdout or "").strip()}
    try:
        payload = json.loads((proc.stdout or "").strip() or "{}")
    except json.JSONDecodeError as exc:
        return 502, {"status": "error", "error": f"invalid_windows_bridge_json:{exc}", "raw": proc.stdout}
    return 200, payload


class Handler(BaseHTTPRequestHandler):
    server_version = "OrbQwenTtsWslProxy/1.0"

    def _send_json(self, status_code: int, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") in {"", "/health"}:
            status_code, payload = _powershell_json("GET", "/health", timeout=20)
            payload = {
                **payload,
                "proxy": "wsl_qwen_tts_proxy",
                "windows_bridge": WINDOWS_BRIDGE,
            }
            self._send_json(status_code, payload)
            return
        self._send_json(404, {"status": "not_found", "path": self.path})

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") not in {"/synthesize", "/tts", "/speak"}:
            self._send_json(404, {"status": "not_found", "path": self.path})
            return
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length).decode("utf-8", errors="replace")
        status_code, payload = _powershell_json("POST", "/synthesize", body=body, timeout=220)
        payload = {
            **payload,
            "proxy": "wsl_qwen_tts_proxy",
            "windows_bridge": WINDOWS_BRIDGE,
        }
        self._send_json(status_code, payload)

    def log_message(self, fmt: str, *args: Any) -> None:
        if os.getenv("ORB_QWEN_TTS_WSL_PROXY_LOG", "0") in {"1", "true", "yes"}:
            super().log_message(fmt, *args)


def main() -> None:
    server = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), Handler)
    print(f"WSL Qwen TTS proxy listening on http://{LISTEN_HOST}:{LISTEN_PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
