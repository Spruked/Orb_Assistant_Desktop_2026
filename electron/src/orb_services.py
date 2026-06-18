#!/usr/bin/env python3
"""Orb services — service manifest, status probing, start/stop/open control."""

import json
import socket
import subprocess
import urllib.request
from datetime import datetime
from pathlib import Path


class OrbServices:
    """Service control layer for the Orb."""

    def __init__(self, core_knowledge=None):
        self.core_knowledge = core_knowledge
        self.service_status_cache = {}

    def load_service_manifest(self):
        services = self.core_knowledge.load_services() if self.core_knowledge else []
        normalized = []
        for service in services:
            if not isinstance(service, dict):
                continue
            item = dict(service)
            service_id = (
                item.get("service_id")
                or item.get("id")
                or str(item.get("domain", "")).split(".")[0]
            )
            domain = item.get("domain") or service_id
            start_command = item.get("start_command") or (item.get("commands") or {}).get("start") or ""
            stop_command = item.get("stop_command") or (item.get("commands") or {}).get("stop") or ""
            expected_ports = item.get("expected_ports") or []
            if isinstance(expected_ports, str):
                expected_ports = [p.strip() for p in expected_ports.split(",") if p.strip()]
            expected_ports = [
                int(p) for p in expected_ports
                if str(p).strip().isdigit()
            ]
            local_url = str(item.get("local_url") or "").strip()
            health_url = str(item.get("health_url") or item.get("status_url") or "").strip()
            if not health_url:
                health_url = local_url
            public_url = str(item.get("public_url") or "").strip() or f"https://{domain}"
            working_directory = str(item.get("working_directory") or item.get("repo_path") or "").strip()
            service_type = str(item.get("service_type") or "website").strip() or "website"

            normalized_item = {
                "service_id": str(service_id),
                "instance_id": str(item.get("instance_id") or "wsl"),
                "display_name": str(item.get("display_name") or domain),
                "domain": str(domain),
                "public_url": public_url,
                "local_url": local_url,
                "health_url": health_url,
                "working_directory": working_directory,
                "expected_ports": expected_ports,
                "service_type": service_type,
                "enabled": bool(item.get("enabled", True)),
                "start_command": str(start_command).strip(),
                "stop_command": str(stop_command).strip(),
                "id": str(service_id),
                "repo_path": working_directory,
                "status_url": health_url,
                "commands": {
                    "start": str(start_command).strip(),
                    "stop": str(stop_command).strip(),
                    "status": str((item.get("commands") or {}).get("status") or "").strip(),
                },
            }
            normalized.append(normalized_item)
        return normalized

    def _find_service(self, service_id):
        target = str(service_id or "").strip().lower()
        for service in self.load_service_manifest():
            candidates = {
                str(service.get("service_id", "")).lower(),
                str(service.get("id", "")).lower(),
                str(service.get("domain", "")).lower(),
                str(service.get("public_url", "")).lower(),
                str(service.get("display_name", "")).lower(),
            }
            if target in candidates:
                return service
        return None

    def _probe_expected_ports(self, expected_ports):
        checks = []
        for port in expected_ports or []:
            port_value = int(port)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.6)
            try:
                reachable = sock.connect_ex(("127.0.0.1", port_value)) == 0
            except Exception:
                reachable = False
            finally:
                sock.close()
            checks.append({"port": port_value, "listening": reachable})
        return checks

    def _service_status(self, service, probe_network=True):
        working_directory = str(service.get("working_directory") or service.get("repo_path") or "").strip()
        health_url = str(service.get("health_url") or service.get("status_url") or service.get("local_url") or "").strip()
        expected_ports = service.get("expected_ports") or []
        port_checks = self._probe_expected_ports(expected_ports)
        listening_ports = [entry["port"] for entry in port_checks if entry.get("listening")]
        enabled = bool(service.get("enabled", True))
        status = {
            "enabled": enabled,
            "configured": bool(
                health_url
                or working_directory
                or service.get("start_command")
                or service.get("stop_command")
                or expected_ports
            ),
            "working_directory": working_directory or None,
            "working_directory_exists": Path(working_directory).expanduser().exists() if working_directory else False,
            "health_url": health_url or None,
            "reachable": None,
            "status_code": None,
            "expected_ports": expected_ports,
            "port_checks": port_checks,
            "ports_listening": listening_ports,
            "running": bool(listening_ports),
            "checked_at": datetime.utcnow().isoformat() + "Z",
        }
        if health_url and probe_network:
            try:
                with urllib.request.urlopen(health_url, timeout=2) as response:
                    status["reachable"] = 200 <= int(response.status) < 500
                    status["status_code"] = int(response.status)
            except Exception as exc:
                status["reachable"] = False
                status["error"] = str(exc)
        if status["reachable"] is None:
            status["reachable"] = bool(listening_ports)
        return status

    def handle_service_control(self, service_id, action):
        service = self._find_service(service_id)
        normalized_action = str(action or "status").strip().lower()
        if not service:
            return {
                "status": "not_found",
                "error": f"Service not found: {service_id}",
                "service_id": service_id,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }

        if normalized_action == "open":
            url = service.get("local_url") or service.get("public_url")
            return {
                "status": "success",
                "action": "open",
                "service": service,
                "url": url,
                "result": f"Open requested for {service.get('display_name') or service.get('domain')}.",
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }

        if normalized_action == "status":
            service_status = self._service_status(service, probe_network=True)
            self.service_status_cache[str(service.get("service_id") or service.get("id"))] = service_status
            return {
                "status": "success",
                "action": "status",
                "service": service,
                "service_status": service_status,
                "status_code": service_status.get("status_code"),
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }

        if normalized_action not in {"start", "stop"}:
            return {
                "status": "error",
                "error": f"Unsupported service action: {normalized_action}",
                "service": service,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }

        command = str(service.get(f"{normalized_action}_command") or "").strip()
        if not command:
            return {
                "status": "needs_configuration",
                "error": f"{normalized_action} command is not configured for {service.get('display_name') or service.get('domain')}.",
                "action": normalized_action,
                "service": service,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }

        cwd = str(service.get("working_directory") or "").strip() or None
        if cwd and not Path(cwd).expanduser().exists():
            return {
                "status": "error",
                "error": f"Configured working_directory does not exist: {cwd}",
                "action": normalized_action,
                "service": service,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }
        try:
            proc = subprocess.Popen(command, shell=True, cwd=cwd)
            process_result = {
                "exit_code": 0,
                "pid": int(getattr(proc, "pid", 0) or 0),
                "stdout": "",
                "stderr": "",
            }
        except Exception as exc:
            return {
                "status": "error",
                "error": str(exc),
                "action": normalized_action,
                "service": service,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }
        service_status = self._service_status(service, probe_network=True)
        self.service_status_cache[str(service.get("service_id") or service.get("id"))] = service_status
        return {
            "status": "success",
            "action": normalized_action,
            "service": service,
            "result": f"{normalized_action} requested for {service.get('display_name') or service.get('domain')}.",
            "process_result": process_result,
            "status_code": service_status.get("status_code"),
            "service_status": service_status,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
