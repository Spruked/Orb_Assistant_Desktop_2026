import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

try:
    import psutil
except Exception:
    psutil = None

from cali_skills.core.interface import CALISkill


class SystemSkill(CALISkill):
    """Core system operations skill."""

    DEFAULT_ALLOWED_COMMANDS = ["ls", "dir", "echo", "python", "node", "npm", "pip", "git"]
    ALLOWED_ROOTS = ["R:\\", "/mnt/r/"]

    def _load_metadata(self) -> Dict[str, Any]:
        return self.config

    def can_handle(self, intent: str, context: Dict[str, Any]) -> float:
        intent_lower = str(intent or "").lower()
        triggers = self.config.get("triggers", [])
        if any(trigger in intent_lower for trigger in triggers):
            return 0.95
        command_indicators = ["show me", "get", "list", "read", "write", "create", "delete", "kill", "check"]
        file_indicators = [".txt", ".json", ".py", ".md", "file", "folder", "directory"]
        if any(item in intent_lower for item in command_indicators) and any(item in intent_lower for item in file_indicators):
            return 0.85
        return 0.1

    def execute(self, command: str, params: Dict[str, Any], memory: Any) -> Dict[str, Any]:
        try:
            dispatch = {
                "read_file": self._read_file,
                "write_file": self._write_file,
                "append_file": self._append_file,
                "list_directory": self._list_directory,
                "list_dir": self._list_directory,
                "exec_command": self._exec_command,
                "sys_info": self._sys_info,
                "path_exists": self._path_exists,
                "create_directory": self._create_directory,
                "delete_file": self._delete_file,
                "file_stats": self._file_stats,
                "process_list": self._process_list,
                "kill_process": self._kill_process,
                "disk_usage": self._disk_usage,
                "env_vars": self._env_vars,
            }
            handler = dispatch.get(command)
            if not handler:
                return {"status": "error", "error": f"Unknown command: {command}", "confidence": 1.0}
            return handler(params or {})
        except Exception as exc:
            return {
                "status": "error",
                "error": str(exc),
                "command": command,
                "timestamp": datetime.utcnow().isoformat(),
                "confidence": 1.0,
            }

    def _read_file(self, params: Dict[str, Any]) -> Dict[str, Any]:
        path = Path(params.get("path", "")).expanduser().resolve()
        if not self._is_path_allowed(path):
            return {"status": "error", "error": "Path access denied", "confidence": 1.0}
        if not path.exists():
            return {"status": "error", "error": f"File not found: {path}", "confidence": 1.0}
        try:
            content = path.read_text(encoding="utf-8")
            return {"status": "success", "result": content, "path": str(path), "size": len(content), "confidence": 0.98}
        except UnicodeDecodeError:
            content = path.read_bytes()
            return {"status": "success", "result": f"<binary data: {len(content)} bytes>", "path": str(path), "binary": True, "confidence": 0.98}

    def _write_file(self, params: Dict[str, Any]) -> Dict[str, Any]:
        path = Path(params.get("path", "")).expanduser().resolve()
        content = params.get("content", "")
        mode = params.get("mode", "w")
        if not self._is_path_allowed(path):
            return {"status": "error", "error": "Path access denied", "confidence": 1.0}
        path.parent.mkdir(parents=True, exist_ok=True)
        if mode == "wb":
            data = content.encode("utf-8") if isinstance(content, str) else content
            path.write_bytes(data)
            bytes_written = len(data)
        else:
            text = str(content)
            path.write_text(text, encoding="utf-8")
            bytes_written = len(text.encode("utf-8"))
        return {"status": "success", "path": str(path), "bytes_written": bytes_written, "confidence": 0.99}

    def _append_file(self, params: Dict[str, Any]) -> Dict[str, Any]:
        path = Path(params.get("path", "")).expanduser().resolve()
        content = str(params.get("content", ""))
        if not self._is_path_allowed(path):
            return {"status": "error", "error": "Path access denied", "confidence": 1.0}
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(content)
        return {"status": "success", "path": str(path), "appended": len(content), "confidence": 0.99}

    def _list_directory(self, params: Dict[str, Any]) -> Dict[str, Any]:
        path = Path(params.get("path", ".")).expanduser().resolve()
        if not self._is_path_allowed(path):
            return {"status": "error", "error": "Path access denied", "confidence": 1.0}
        if not path.exists():
            return {"status": "error", "error": f"Directory not found: {path}", "confidence": 1.0}
        items = []
        for item in path.iterdir():
            stat = item.stat()
            items.append({
                "name": item.name,
                "type": "directory" if item.is_dir() else "file",
                "size": stat.st_size if item.is_file() else None,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "path": str(item),
            })
        return {"status": "success", "path": str(path), "items": items, "count": len(items), "confidence": 0.98}

    def _exec_command(self, params: Dict[str, Any]) -> Dict[str, Any]:
        cmd = str(params.get("cmd") or "").strip()
        if not cmd:
            return {"status": "error", "error": "Empty command", "confidence": 1.0}
        allowed_commands = params.get("allowed_commands")
        if not allowed_commands:
            allowed_commands = list(self.DEFAULT_ALLOWED_COMMANDS)
            allowed_commands.extend(self.config.get("allowed_commands") or [])
        if isinstance(allowed_commands, str):
            allowed_commands = [allowed_commands]
        base_cmd = cmd.split()[0].lower()
        if base_cmd not in {str(item).lower() for item in allowed_commands}:
            return {"status": "error", "error": f"Command '{base_cmd}' not allowed", "confidence": 1.0}
        cwd = params.get("cwd")
        if cwd and not self._is_path_allowed(Path(cwd).expanduser().resolve()):
            return {"status": "error", "error": "cwd access denied", "confidence": 1.0}
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                cwd=cwd,
                env={**os.environ, **(params.get("env") or {})},
                timeout=int(params.get("timeout", 30)),
            )
        except subprocess.TimeoutExpired:
            return {"status": "error", "error": "Command timed out", "confidence": 1.0}
        return {"status": "success" if result.returncode == 0 else "error", "stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode, "confidence": 0.95}

    def _sys_info(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            user = os.getlogin()
        except Exception:
            user = os.environ.get("USERNAME") or os.environ.get("USER") or "unknown"
        return {
            "status": "success",
            "platform": sys.platform,
            "platform_detail": platform.platform(),
            "python_version": sys.version,
            "cpu_count": os.cpu_count(),
            "hostname": platform.node() or os.environ.get("COMPUTERNAME", "unknown"),
            "user": user,
            "confidence": 0.99,
        }

    def _path_exists(self, params: Dict[str, Any]) -> Dict[str, Any]:
        path = Path(params.get("path", "")).expanduser().resolve()
        if not self._is_path_allowed(path):
            return {"status": "error", "error": "Path access denied", "confidence": 1.0}
        exists = path.exists()
        return {"status": "success", "exists": exists, "is_file": path.is_file() if exists else False, "is_dir": path.is_dir() if exists else False, "confidence": 1.0}

    def _create_directory(self, params: Dict[str, Any]) -> Dict[str, Any]:
        path = Path(params.get("path", "")).expanduser().resolve()
        if not self._is_path_allowed(path):
            return {"status": "error", "error": "Path access denied", "confidence": 1.0}
        path.mkdir(parents=bool(params.get("parents", True)), exist_ok=bool(params.get("exist_ok", True)))
        return {"status": "success", "path": str(path), "created": True, "confidence": 0.99}

    def _delete_file(self, params: Dict[str, Any]) -> Dict[str, Any]:
        path = Path(params.get("path", "")).expanduser().resolve()
        if not params.get("confirm"):
            return {"status": "needs_confirmation", "error": "delete_file requires confirm=True", "confidence": 1.0}
        if not self._is_path_allowed(path):
            return {"status": "error", "error": "Path access denied", "confidence": 1.0}
        if not path.exists():
            return {"status": "error", "error": f"Path does not exist: {path}", "confidence": 1.0}
        if path.is_file():
            path.unlink()
        elif path.is_dir() and params.get("recursive"):
            shutil.rmtree(path)
        else:
            return {"status": "error", "error": "Is directory (use recursive=True)", "confidence": 1.0}
        return {"status": "success", "deleted": str(path), "confidence": 0.99}

    def _file_stats(self, params: Dict[str, Any]) -> Dict[str, Any]:
        path = Path(params.get("path", "")).expanduser().resolve()
        if not self._is_path_allowed(path):
            return {"status": "error", "error": "Path access denied", "confidence": 1.0}
        stat = path.stat()
        return {
            "status": "success",
            "path": str(path),
            "size": stat.st_size,
            "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "accessed": datetime.fromtimestamp(stat.st_atime).isoformat(),
            "confidence": 0.98,
        }

    def _process_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if psutil is None:
            return {"status": "missing_dependency", "error": "psutil is not installed", "confidence": 1.0}
        processes = []
        for proc in psutil.process_iter(["pid", "name", "status", "cpu_percent", "memory_percent"]):
            try:
                processes.append(proc.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return {"status": "success", "processes": processes, "count": len(processes), "confidence": 0.95}

    def _kill_process(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if psutil is None:
            return {"status": "missing_dependency", "error": "psutil is not installed", "confidence": 1.0}
        if not params.get("confirm"):
            return {"status": "needs_confirmation", "error": "kill_process requires confirm=True", "confidence": 1.0}
        pid = int(params.get("pid"))
        proc = psutil.Process(pid)
        proc.terminate()
        return {"status": "success", "pid": pid, "terminated": True, "confidence": 0.95}

    def _disk_usage(self, params: Dict[str, Any]) -> Dict[str, Any]:
        path = Path(params.get("path", Path.cwd().anchor or ".")).expanduser().resolve()
        if not self._is_path_allowed(path):
            return {"status": "error", "error": "Path access denied", "confidence": 1.0}
        if psutil is None:
            usage = shutil.disk_usage(path)
            return {"status": "success", "total": usage.total, "used": usage.used, "free": usage.free, "percent": round((usage.used / usage.total) * 100, 2), "confidence": 0.95}
        usage = psutil.disk_usage(path)
        return {"status": "success", "total": usage.total, "used": usage.used, "free": usage.free, "percent": usage.percent, "path": str(path), "confidence": 0.98}

    def _env_vars(self, params: Dict[str, Any]) -> Dict[str, Any]:
        key = params.get("key")
        if key:
            return {"status": "success", "key": key, "value": os.environ.get(key), "exists": key in os.environ, "confidence": 0.99}
        safe_env = {k: v for k, v in os.environ.items() if not any(secret in k.lower() for secret in ["key", "token", "secret", "password"])}
        return {"status": "success", "env": safe_env, "count": len(safe_env), "confidence": 0.99}

    def _is_path_allowed(self, path: Path) -> bool:
        try:
            resolved = str(path.resolve())
        except Exception:
            return False
        win_path = resolved.replace("/", "\\").lower()
        posix_path = resolved.replace("\\", "/").lower()
        allowed_roots = list(self.ALLOWED_ROOTS)
        allowed_roots.extend(self.config.get("allowed_roots") or [])
        for root in allowed_roots:
            root_text = str(root)
            win_root = root_text.replace("/", "\\").lower().rstrip("\\") + "\\"
            posix_root = root_text.replace("\\", "/").lower().rstrip("/") + "/"
            if win_path.startswith(win_root) or posix_path.startswith(posix_root):
                return True
        return False

    def get_memory_scope(self) -> List[str]:
        return ["skills/system", "system_cache", "file_index"]
