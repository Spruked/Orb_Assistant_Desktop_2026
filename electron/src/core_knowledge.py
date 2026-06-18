#!/usr/bin/env python3
"""CaliCoreKnowledge — seeded knowledge base for Orb system awareness."""

import json
import re
import subprocess
from datetime import datetime
from pathlib import Path


class CaliCoreKnowledge:
    def __init__(self, base_path):
        self.base_path = Path(base_path).expanduser().resolve()
        self.base_path.mkdir(parents=True, exist_ok=True)
        self._ensure_seed_files()

    def _ensure_seed_files(self):
        seeds = {
            "truemark_mint": {
                "overview.txt": (
                    "TrueMark Mint is the local-first sovereign certification and document vault system. "
                    "Its role is to support certified, timestamped, operator-controlled records without "
                    "merging website and engine responsibilities.\n"
                ),
                "commands.json": json.dumps(
                    {
                        "start": "start truemark",
                        "open": "open truemark",
                        "status": "truemark status",
                    },
                    indent=2,
                )
                + "\n",
                "launch.json": json.dumps(
                    {
                        "name": "truemark_mint",
                        "type": "wsl_service",
                        "command": "",
                        "cwd": "",
                        "notes": "Set command/cwd after the local TrueMark Mint service path is confirmed.",
                    },
                    indent=2,
                )
                + "\n",
            },
            "goat_system": {
                "overview.txt": (
                    "GOAT is the preservation and book-building system family used for structured knowledge "
                    "capture, preservation workflows, and later publication/export paths. CALI should explain "
                    "GOAT from curated local files first.\n"
                ),
                "structure.json": json.dumps(
                    {
                        "known_roots": ["R:\\goat_substrate"],
                        "notes": "Add exact GOAT_Preservation_System paths when present on this machine.",
                    },
                    indent=2,
                )
                + "\n",
            },
            "spruked": {
                "overview.txt": (
                    "Spruked is the operator ecosystem around the Orb assistant and related websites/services. "
                    "Known website surfaces include spruked.com, truemarkmint.com, shilohridgekatahdins.com, "
                    "alphacertsig.com, and dragonithome.spruked.com.\n"
                ),
                "sites.json": json.dumps(
                    {
                        "sites": [
                            "spruked.com",
                            "truemarkmint.com",
                            "shilohridgekatahdins.com",
                            "alphacertsig.com",
                            "dragonithome.spruked.com",
                        ]
                    },
                    indent=2,
                )
                + "\n",
                "services.json": json.dumps(
                    {
                        "services": [
                            {
                                "service_id": "spruked",
                                "instance_id": "dockstation-default",
                                "display_name": "Spruked",
                                "domain": "spruked.com",
                                "public_url": "https://spruked.com",
                                "local_url": "",
                                "health_url": "https://spruked.com",
                                "working_directory": "",
                                "expected_ports": [],
                                "service_type": "website",
                                "enabled": True,
                                "start_command": "",
                                "stop_command": "",
                            },
                            {
                                "service_id": "truemarkmint",
                                "instance_id": "dockstation-default",
                                "display_name": "TrueMark Mint",
                                "domain": "truemarkmint.com",
                                "public_url": "https://truemarkmint.com",
                                "local_url": "",
                                "health_url": "https://truemarkmint.com",
                                "working_directory": "",
                                "expected_ports": [],
                                "service_type": "website",
                                "enabled": True,
                                "start_command": "",
                                "stop_command": "",
                            },
                            {
                                "service_id": "shilohridgekatahdins",
                                "instance_id": "dockstation-default",
                                "display_name": "Shiloh Ridge Katahdins",
                                "domain": "shilohridgekatahdins.com",
                                "public_url": "https://shilohridgekatahdins.com",
                                "local_url": "",
                                "health_url": "https://shilohridgekatahdins.com",
                                "working_directory": "",
                                "expected_ports": [],
                                "service_type": "website",
                                "enabled": True,
                                "start_command": "",
                                "stop_command": "",
                            },
                            {
                                "service_id": "alphacertsig",
                                "instance_id": "dockstation-default",
                                "display_name": "AlphaCertSig",
                                "domain": "alphacertsig.com",
                                "public_url": "https://alphacertsig.com",
                                "local_url": "",
                                "health_url": "https://alphacertsig.com",
                                "working_directory": "",
                                "expected_ports": [],
                                "service_type": "website",
                                "enabled": True,
                                "start_command": "",
                                "stop_command": "",
                            },
                            {
                                "service_id": "dragonithome",
                                "instance_id": "dockstation-default",
                                "display_name": "DragonItHome",
                                "domain": "dragonithome.spruked.com",
                                "public_url": "https://dragonithome.spruked.com",
                                "local_url": "",
                                "health_url": "https://dragonithome.spruked.com",
                                "working_directory": "",
                                "expected_ports": [],
                                "service_type": "website",
                                "enabled": True,
                                "start_command": "",
                                "stop_command": "",
                            },
                        ]
                    },
                    indent=2,
                )
                + "\n",
            },
        }
        for subject, files in seeds.items():
            subject_path = self.base_path / subject
            subject_path.mkdir(parents=True, exist_ok=True)
            for filename, content in files.items():
                path = subject_path / filename
                if not path.exists():
                    path.write_text(content, encoding="utf-8")

    def _subject_for_query(self, query):
        lowered = str(query or "").lower()
        if "truemark" in lowered or "true mark" in lowered:
            return "truemark_mint"
        if "goat" in lowered:
            return "goat_system"
        if "spruked" in lowered or "dragonit" in lowered or "alphacertsig" in lowered:
            return "spruked"
        return None

    def load_core(self, subject):
        subject_path = self.base_path / subject
        if not subject_path.exists():
            return None
        payload = {"subject": subject, "path": str(subject_path), "files": {}}
        for path in sorted(subject_path.iterdir()):
            if path.suffix.lower() not in {".txt", ".json"}:
                continue
            try:
                if path.suffix.lower() == ".json":
                    payload["files"][path.name] = json.loads(path.read_text(encoding="utf-8"))
                else:
                    payload["files"][path.name] = path.read_text(encoding="utf-8").strip()
            except Exception:
                payload["files"][path.name] = ""
        return payload

    def handle(self, query):
        subject = self._subject_for_query(query)
        if not subject:
            return None
        lowered = str(query or "").lower()
        core = self.load_core(subject)
        if not core:
            return None

        if any(term in lowered for term in ("start ", "launch ", "open ", "status")):
            return {"subject": subject, "action": "operator_command", "core": core}

        overview = core["files"].get("overview.txt", "")
        action_line = ""
        commands = core["files"].get("commands.json")
        if isinstance(commands, dict):
            action_line = " I can start it, open it, or check status if the local launch command is configured."
        return {
            "subject": subject,
            "action": "explain",
            "core": core,
            "response_text": (overview + action_line).strip(),
        }

    def load_services(self):
        core = self.load_core("spruked") or {}
        services = core.get("files", {}).get("services.json", {})
        if isinstance(services, dict):
            return services.get("services", [])
        return []
