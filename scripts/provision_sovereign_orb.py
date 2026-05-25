#!/usr/bin/env python3
"""Provision a sovereign desktop ORB instance and shared mesh scaffold."""

from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


REPO_EXCLUDES = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    "node_modules",
    "dist",
    ".orb-assistant",
    ".orb-assistant-wsl",
    ".orb-assistant-desktop",
    "audio_cache",
    "venv",
}

PATH_PREFIX_EXCLUDES = {
    "CALI_System/cache",
    "CALI_System/logs",
    "CALI_System/memory",
    "CALI_System/swarm_results",
    "CALI_System/voice_cache",
    "electron/audio_cache",
    "electron/src/audio_cache",
    "electron/src/vault_system",
    "vault_system",
}

FILE_NAME_EXCLUDES = {
    "tree.txt",
    "folder_tree.txt",
}

SUFFIX_EXCLUDES = {
    ".pyc",
    ".pyo",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def should_ignore(path: Path, root: Path) -> bool:
    relative_path = path.relative_to(root)
    relative_parts = relative_path.parts
    if any(part in REPO_EXCLUDES for part in relative_parts):
        return True
    relative_str = relative_path.as_posix()
    if any(
        relative_str == prefix or relative_str.startswith(f"{prefix}/")
        for prefix in PATH_PREFIX_EXCLUDES
    ):
        return True
    if path.name in FILE_NAME_EXCLUDES:
        return True
    return path.suffix in SUFFIX_EXCLUDES


def copy_repo(source_root: Path, target_root: Path) -> None:
    if target_root.exists():
        raise FileExistsError(f"Target already exists: {target_root}")

    def _ignore(directory: str, names: Iterable[str]) -> set[str]:
        ignored: set[str] = set()
        base = Path(directory)
        for name in names:
            candidate = base / name
            if should_ignore(candidate, source_root):
                ignored.add(name)
        return ignored

    shutil.copytree(source_root, target_root, ignore=_ignore)


def write_text(path: Path, content: str, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if executable:
        path.chmod(0o755)


def write_json(path: Path, payload: object) -> None:
    write_text(path, json.dumps(payload, indent=2) + "\n")


def bootstrap_runtime_system(source_root: Path, system_root: Path) -> None:
    cali_root = system_root / "CALI_System"
    for folder in (
        "config",
        "cache",
        "logs",
        "memory/a_priori",
        "memory/a_posteriori",
        "memory/patterns",
        "swarm_results",
        "voice_cache",
    ):
        (cali_root / folder).mkdir(parents=True, exist_ok=True)

    for filename in ("api_registry.json", "advanced_api_imports.json"):
        source_file = source_root / "CALI_System" / "config" / filename
        if source_file.exists():
            write_text(
                cali_root / "config" / filename,
                source_file.read_text(encoding="utf-8"),
            )


def create_mesh(mesh_root: Path, wsl_root: Path, desktop_root: Path) -> None:
    folders = [
        "manifests",
        "exports/wsl/insights",
        "exports/wsl/embeddings",
        "exports/wsl/indexes",
        "exports/wsl/capabilities",
        "exports/wsl/state_snapshots",
        "exports/desktop/insights",
        "exports/desktop/embeddings",
        "exports/desktop/indexes",
        "exports/desktop/capabilities",
        "exports/desktop/state_snapshots",
        "imports/wsl",
        "imports/desktop",
        "tasks/wsl_to_desktop",
        "tasks/desktop_to_wsl",
        "tasks/broadcast",
        "results/wsl",
        "results/desktop",
        "results/shared",
        "promoted_knowledge",
        "checkpoints/wsl",
        "checkpoints/desktop",
        "locks",
        "audit",
    ]

    for folder in folders:
        (mesh_root / folder).mkdir(parents=True, exist_ok=True)

    readme = """# ORB Mesh

Shared knowledge and task plane for sovereign ORB instances.

Principles
- Each ORB keeps its own local memory and system state.
- Only selected artifacts are published here.
- Imports are pull-based and checkpointed.
- Tasks and results are append-only, source-tagged artifacts.

Core folders
- `exports/`: high-value artifacts published by each ORB
- `imports/`: per-ORB import staging and receipts
- `tasks/`: task handoff queues
- `results/`: task outcomes and shared synthesis
- `promoted_knowledge/`: curated cross-ORB knowledge promoted above raw exports
- `checkpoints/`: per-ORB sync cursors and receipts
- `locks/`: optional cooperative file locks
- `audit/`: mesh activity and sync logs
"""
    write_text(mesh_root / "README.md", readme)

    write_json(
        mesh_root / "manifests" / "mesh_protocol.json",
        {
            "schema_version": "1.0",
            "mesh_name": "orb_mesh",
            "created_at": utc_now(),
            "artifact_envelope": {
                "artifact_id": "uuid-or-hash",
                "artifact_type": "insight|embedding_manifest|index_manifest|task|result|state_snapshot",
                "source_orb": "wsl|desktop",
                "target_orb": "desktop|wsl|broadcast|shared",
                "created_at": "ISO-8601 UTC",
                "updated_at": "ISO-8601 UTC",
                "confidence": 0.0,
                "priority": "low|normal|high",
                "content_hash": "sha256...",
                "tags": [],
                "payload": {},
            },
            "task_flow": {
                "publish_paths": [
                    "tasks/wsl_to_desktop",
                    "tasks/desktop_to_wsl",
                    "tasks/broadcast",
                ],
                "result_paths": [
                    "results/wsl",
                    "results/desktop",
                    "results/shared",
                ],
            },
            "sync_rules": [
                "Each ORB publishes selected high-value artifacts only.",
                "Each ORB tracks imported artifacts with checkpoints.",
                "Promotion into promoted_knowledge is curated or policy-driven.",
            ],
        },
    )

    write_json(
        mesh_root / "manifests" / "orb_registry.json",
        {
            "schema_version": "1.0",
            "created_at": utc_now(),
            "orbs": [
                {
                    "instance_id": "wsl",
                    "role": "forge_and_research",
                    "root": str(wsl_root),
                    "exports_root": str(mesh_root / "exports" / "wsl"),
                    "imports_root": str(mesh_root / "imports" / "wsl"),
                    "checkpoint_root": str(mesh_root / "checkpoints" / "wsl"),
                },
                {
                    "instance_id": "desktop",
                    "role": "desktop_system_orb",
                    "root": str(desktop_root),
                    "exports_root": str(mesh_root / "exports" / "desktop"),
                    "imports_root": str(mesh_root / "imports" / "desktop"),
                    "checkpoint_root": str(mesh_root / "checkpoints" / "desktop"),
                },
            ],
        },
    )

    for instance_id in ("wsl", "desktop"):
        write_json(
            mesh_root / "checkpoints" / instance_id / "sync_state.json",
            {
                "schema_version": "1.0",
                "instance_id": instance_id,
                "last_export_scan": None,
                "last_import_applied": None,
                "last_task_poll": None,
                "notes": "Checkpoint scaffold created during sovereign ORB provisioning.",
            },
        )


def create_instance_files(
    source_root: Path,
    target_root: Path,
    instance_id: str,
    product_name: str,
    app_id: str,
    python_path: str,
    mesh_root: Path,
) -> None:
    state_dir = target_root / f".orb-assistant-{instance_id}"
    system_root = target_root / "system"
    system_root.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)
    bootstrap_runtime_system(source_root, system_root)

    env_content = f"""# Sovereign ORB instance environment
export ORB_INSTANCE_ID="{instance_id}"
export ORB_PRODUCT_NAME="{product_name}"
export ORB_APP_ID="{app_id}"
export ORB_USER_DATA_DIR="{state_dir}"
export ORB_SYSTEM_ROOT="{system_root}"
export ORB_SHARED_MESH_ROOT="{mesh_root}"
export ORB_SINGLE_INSTANCE="0"
export ORB_PYTHON_PATH="{python_path}"
"""
    write_text(target_root / ".orb-instance.env", env_content)

    launch_script = """#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export ORB_INSTANCE_ENV="${ROOT}/.orb-instance.env"
exec "${ROOT}/scripts/launch_orb_instance.sh"
"""
    write_text(target_root / "launch_desktop_orb.sh", launch_script, executable=True)

    write_json(
        target_root / "instance.manifest.json",
        {
            "schema_version": "1.0",
            "created_at": utc_now(),
            "instance_id": instance_id,
            "product_name": product_name,
            "app_id": app_id,
            "root": str(target_root),
            "user_data_dir": str(state_dir),
            "system_root": str(system_root),
            "shared_mesh_root": str(mesh_root),
            "launch_script": str(target_root / "launch_desktop_orb.sh"),
            "python_path": python_path,
        },
    )

    write_text(
        target_root / "SOVEREIGN_INSTANCE.md",
        f"""# {product_name}

This is a sovereign ORB instance provisioned from the WSL forge copy.

Identity
- `instance_id`: `{instance_id}`
- `app_id`: `{app_id}`
- `shared_mesh_root`: `{mesh_root}`

Runtime
- Launch with `./launch_desktop_orb.sh`
- Local user data lives in `{state_dir}`
- Local CALI system data lives under `{system_root / 'CALI_System'}`

Notes
- This instance is designed to coexist with the WSL ORB.
- It shares through the mesh, but it does not depend on the WSL ORB to boot.
""",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-root",
        default=str(Path(__file__).resolve().parents[1]),
        help="Source Orb Assistant repo root.",
    )
    parser.add_argument(
        "--desktop-root",
        default="/mnt/r/Orb_Assistant_Desktop",
        help="Target sovereign desktop instance root.",
    )
    parser.add_argument(
        "--mesh-root",
        default="/mnt/r/orb_mesh",
        help="Shared ORB mesh root.",
    )
    parser.add_argument(
        "--python-path",
        default=os.getenv("ORB_PYTHON_PATH", "/home/bryan/pro_prime_env/bin/python"),
        help="Python executable to use for the desktop instance.",
    )
    args = parser.parse_args()

    source_root = Path(args.source_root).expanduser().resolve()
    desktop_root = Path(args.desktop_root).expanduser().resolve()
    mesh_root = Path(args.mesh_root).expanduser().resolve()

    copy_repo(source_root, desktop_root)
    create_instance_files(
        source_root=source_root,
        target_root=desktop_root,
        instance_id="desktop",
        product_name="Orb Assistant Desktop",
        app_id="com.orbassistant.desktop",
        python_path=args.python_path,
        mesh_root=mesh_root,
    )
    create_mesh(mesh_root, source_root, desktop_root)

    print(
        json.dumps(
            {
                "desktop_root": str(desktop_root),
                "mesh_root": str(mesh_root),
                "created_at": utc_now(),
            }
        )
    )


if __name__ == "__main__":
    main()
