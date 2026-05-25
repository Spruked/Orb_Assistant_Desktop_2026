import json
from pathlib import Path
from typing import Any, Dict, List


class SkillMemoryBridge:
    """Unified local memory access layer for isolated skill memory."""

    def __init__(self, root_path: str):
        self.root_path = Path(root_path).expanduser().resolve()
        self.root_path.mkdir(parents=True, exist_ok=True)

    def scope_path(self, scope: str) -> Path:
        clean = str(scope or "general").strip().replace("\\", "/").strip("/")
        path = self.root_path / clean
        path.mkdir(parents=True, exist_ok=True)
        return path

    def append_jsonl(self, scope: str, filename: str, record: Dict[str, Any]) -> Path:
        path = self.scope_path(scope) / filename
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        return path

    def read_jsonl(self, scope: str, filename: str, limit: int = 100) -> List[Dict[str, Any]]:
        path = self.scope_path(scope) / filename
        if not path.exists():
            return []
        rows = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]:
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
        return rows
