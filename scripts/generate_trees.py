#!/usr/bin/env python3
"""
Regenerate the repository tree documents:

    tree.txt            full file tree (names only)
    structure_tree.txt  directories only, with file counts and ownership notes

Dependency, runtime, cache and archive folders are listed but collapsed so the
documents stay readable. Run from anywhere:

    python scripts/generate_trees.py
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Listed, but their contents are not expanded.
COLLAPSED = {
    "node_modules", "__pycache__", ".git", ".venv", "venv", ".pytest_cache", ".vscode",
    "dist", "_archive", ".orb-assistant", ".orb-assistant-desktop", ".orb-runtime",
    "audio_cache", "voice_cache", "runtime_logs", "runlogs", "logs", "test-results",
    "Code Cache", "GPUCache", "DawnCache", "Local Storage", "Network", "Session Storage",
    "blob_storage", "leveldb", "tesseract", "vendor",
}
# A directory with more entries than this is truncated in tree.txt.
MAX_ENTRIES_PER_DIR = 150

NOTES = {
    "electron": "Electron host: main process, preload, renderer, Dock Station, Python ORB process",
    "electron/main": "Electron main process (windows, IPC, bridge to Python, MCP client)",
    "electron/src": "Renderer (orb-shell.html, orb-renderer.js, Three.js scene), Python ORB runtime, Dock UI",
    "electron/src/ui": "Dock Station / Studio UI (orb-dock-station.*)",
    "mcp": "Desktop MCP server (desktop control tools, pointer runtime, safety guard)",
    "vault_logic_system": "Vault Logic System: modular framework (vaults, engine, glyphs, telemetry) - vendored, tracked in this repo",
    "vault_logic_system/memory": "Framework memory slot: provider + binding. A.I.M.S. is the only memory authority",
    "vault_logic_system/memory/aims": "A.I.M.S. (Agnostic Immutable Memory System) - short-term cache, long-term ledger, vault, SKG",
    "docs": "Contracts, handoffs, reviews",
    "scripts": "Launch, voice stack, packaging and maintenance scripts",
    "system": "Local system configuration and swarm substrate",
    "api": "FastAPI backend (tribunal, health) - not part of the desktop runtime",
    "tools": "Bundled tools (kept out of source commits)",
}


def entries(path: Path):
    try:
        items = list(os.scandir(path))
    except OSError:
        return []
    return sorted(items, key=lambda e: (not e.is_dir(follow_symlinks=False), e.name.lower()))


def file_tree(path: Path, prefix: str, out: list) -> None:
    items = entries(path)
    shown, hidden = items[:MAX_ENTRIES_PER_DIR], max(0, len(items) - MAX_ENTRIES_PER_DIR)
    for index, entry in enumerate(shown):
        last = index == len(shown) - 1 and hidden == 0
        out.append(f"{prefix}{'└── ' if last else '├── '}{entry.name}{' [collapsed]' if entry.is_dir() and entry.name in COLLAPSED else ''}")
        if entry.is_dir(follow_symlinks=False) and entry.name not in COLLAPSED:
            file_tree(Path(entry.path), prefix + ("    " if last else "│   "), out)
    if hidden:
        out.append(f"{prefix}└── ... {hidden} more entries")


def structure(path: Path, depth: int, out: list, counts: dict) -> None:
    for entry in entries(path):
        if not entry.is_dir(follow_symlinks=False):
            continue
        rel = Path(entry.path).relative_to(ROOT).as_posix()
        collapsed = entry.name in COLLAPSED
        direct_files = 0 if collapsed else sum(1 for e in entries(Path(entry.path)) if e.is_file())
        counts["dirs"] += 1
        note = NOTES.get(rel)
        label = f"{'  ' * depth}{entry.name}/" + (" [collapsed]" if collapsed else f"  ({direct_files} files)")
        out.append(label + (f"  - {note}" if note else ""))
        if not collapsed:
            structure(Path(entry.path), depth + 1, out, counts)


def main() -> int:
    stamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
    tree_lines: list = [f"{ROOT.name}/"]
    file_tree(ROOT, "", tree_lines)
    header = [
        f"{ROOT} tree.txt",
        f"Generated: {stamp}",
        "Scope: this repository only. Dependency, runtime, cache and archive folders are collapsed.",
        "Regenerate with: python scripts/generate_trees.py",
        "",
    ]
    (ROOT / "tree.txt").write_text("\n".join(header + tree_lines) + "\n", encoding="utf-8")

    struct_lines: list = []
    counts = {"dirs": 0}
    structure(ROOT, 0, struct_lines, counts)
    top_files = [e.name for e in entries(ROOT) if e.is_file()]
    header = [
        f"{ROOT} structure_tree.txt",
        f"Generated: {stamp}",
        "Scope: this repository only. Directories only; collapsed folders are not expanded.",
        "Regenerate with: python scripts/generate_trees.py",
        "",
        f"Directories ({counts['dirs']}):",
    ]
    footer = ["", f"Top-level files ({len(top_files)}):"] + [f"  {name}" for name in top_files]
    (ROOT / "structure_tree.txt").write_text("\n".join(header + struct_lines + footer) + "\n", encoding="utf-8")
    print(f"tree.txt: {len(tree_lines)} lines; structure_tree.txt: {counts['dirs']} directories")
    return 0


if __name__ == "__main__":
    sys.exit(main())
