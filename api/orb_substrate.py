import json
import logging
import os
import sqlite3
import re
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def _env(name: str, default: str) -> str:
    value = str(os.getenv(name, "")).strip()
    return value or default


def resolve_mesh_file(mesh_root: Path | str, filename: str) -> Path:
    """
    Resolve ORB mesh files using manifests/ first, with root fallback for legacy compatibility.
    """
    mesh_root = Path(mesh_root)
    canonical = mesh_root / "manifests" / filename
    legacy = mesh_root / filename

    if canonical.exists():
        return canonical

    if legacy.exists():
        logging.warning(
            "Legacy ORB mesh path detected for %s. Please migrate this file to %s",
            filename,
            canonical,
        )
        return legacy

    return canonical


class OrbSubstrateService:
    def __init__(self) -> None:
        self.crm_db_path = _env("ORB_CRM_DB_PATH", "R:/R_Drive_Substrate/crm/memory/cali_personal.db")
        self.email_db_path = _env("ORB_EMAIL_DB_PATH", "R:/email_client/emails.db")
        self.crm_api_url = _env("ORB_CRM_API_URL", "http://127.0.0.1:21000").rstrip("/")
        self.email_api_url = _env("ORB_EMAIL_API_URL", "http://127.0.0.1:19000/api").rstrip("/")
        self.admin_token = _env("ORB_ADMIN_TOKEN", _env("CALI_ADMIN_TOKEN", ""))
        self.orb_tier = _env("ORB_TIER", "desktop")
        self.mesh_root = Path(_env("ORB_MESH_ROOT", _env("ORB_SHARED_MESH_ROOT", "R:/R_Drive_Substrate/orb_mesh")))
        self.service_registry: dict[str, Any] = {}
        self.api_manifest: dict[str, Any] = {}
        self.permissions_manifest: dict[str, Any] = {}
        self.manifest_validation_status: dict[str, Any] = {}
        self.access_mode = _env("ORB_ACCESS_MODE", "normal").strip().lower()
        self.permission_flags = self._load_permission_flags()
        self._load_mesh_manifests()

    def _env_bool(self, name: str, default: str = "0") -> bool:
        return _env(name, default).strip().lower() in {"1", "true", "yes", "on"}

    def _load_permission_flags(self) -> dict[str, bool]:
        return {
            "allow_notes": self._env_bool("ORB_ALLOW_NOTES", "1"),
            "allow_activity_write": self._env_bool("ORB_ALLOW_ACTIVITY_WRITE", "1"),
            "allow_email_drafts": self._env_bool("ORB_ALLOW_EMAIL_DRAFTS", "1"),
            "allow_email_send": self._env_bool("ORB_ALLOW_EMAIL_SEND", "0"),
            "allow_contact_delete": self._env_bool("ORB_ALLOW_CONTACT_DELETE", "0"),
            "allow_contact_merge": self._env_bool("ORB_ALLOW_CONTACT_MERGE", "0"),
            "allow_stage_change": self._env_bool("ORB_ALLOW_STAGE_CHANGE", "0"),
        }

    def _read_json_file(self, path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _load_mesh_manifests(self) -> None:
        service_registry_path = resolve_mesh_file(self.mesh_root, "service_registry.json")
        api_manifest_path = resolve_mesh_file(self.mesh_root, "api_manifest.json")
        orb_permissions_path = resolve_mesh_file(self.mesh_root, "orb_permissions.json")

        errors: list[str] = []
        loaded: dict[str, bool] = {
            "service_registry_loaded": False,
            "api_manifest_loaded": False,
            "orb_permissions_loaded": False,
        }
        resolved_paths = {
            "service_registry_path": service_registry_path.as_posix(),
            "api_manifest_path": api_manifest_path.as_posix(),
            "orb_permissions_path": orb_permissions_path.as_posix(),
        }
        self.service_registry = {}
        self.api_manifest = {}
        self.permissions_manifest = {}

        for key, path in (
            ("service_registry_loaded", service_registry_path),
            ("api_manifest_loaded", api_manifest_path),
            ("orb_permissions_loaded", orb_permissions_path),
        ):
            if not path.exists():
                errors.append(f"missing:{path.as_posix()}")
                continue
            try:
                payload = self._read_json_file(path)
                if not isinstance(payload, dict):
                    errors.append(f"malformed_not_object:{path.as_posix()}")
                    continue
                loaded[key] = True
                if key == "service_registry_loaded":
                    self.service_registry = payload
                elif key == "api_manifest_loaded":
                    self.api_manifest = payload
                elif key == "orb_permissions_loaded":
                    self.permissions_manifest = payload
            except Exception as exc:
                errors.append(f"malformed_json:{path.as_posix()}:{exc}")

        required_contract_ok = bool(self.service_registry.get("authorities")) and bool(self.service_registry.get("services"))
        tools_ok = isinstance(self.api_manifest.get("tools"), dict) and len(self.api_manifest.get("tools", {})) > 0
        perms_ok = isinstance(self.permissions_manifest.get("rules"), dict)
        valid = all(loaded.values()) and required_contract_ok and tools_ok and perms_ok
        state = "valid" if valid else "degraded"
        self.manifest_validation_status = {
            "state": state,
            "valid": valid,
            "errors": errors,
            "resolved_paths": resolved_paths,
            **loaded,
        }

        canonical = self.service_registry.get("canonical_paths", {})
        authorities = self.service_registry.get("authorities", {})
        services = self.service_registry.get("services", {})
        if canonical.get("crm_db_path"):
            self.crm_db_path = canonical["crm_db_path"]
        if canonical.get("prime_mail_db_path"):
            self.email_db_path = canonical["prime_mail_db_path"]
        if services.get("cali_crm", {}).get("api_base"):
            self.crm_api_url = str(services["cali_crm"]["api_base"]).rstrip("/")
        if services.get("prime_mail", {}).get("api_base"):
            self.email_api_url = str(services["prime_mail"]["api_base"]).rstrip("/")
        self.data_authority_contract = {
            "mail_authority": authorities.get("mail_authority", "prime_mail"),
            "contact_authority": authorities.get("contact_authority", "cali_crm"),
            "orb_role": authorities.get("orb_role", "operator_assistant_layer"),
        }

    def _connect(self, db_path: str) -> sqlite3.Connection:
        conn = sqlite3.connect(db_path, timeout=15, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _http_json(
        self,
        method: str,
        url: str,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        target = url
        if params:
            clean = {k: v for k, v in params.items() if v is not None and v != ""}
            if clean:
                target = f"{url}?{urlencode(clean)}"
        headers = {"Content-Type": "application/json"}
        if self.admin_token:
            headers["X-Admin-Token"] = self.admin_token
        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
        request = Request(target, data=body, headers=headers, method=method.upper())
        try:
            with urlopen(request, timeout=6) as response:
                raw = response.read().decode("utf-8", errors="replace")
                data = json.loads(raw) if raw else {}
                return {
                    "ok": True,
                    "status_code": int(getattr(response, "status", 200)),
                    "data": data,
                    "url": target,
                }
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else ""
            parsed = None
            try:
                parsed = json.loads(raw) if raw else None
            except Exception:
                parsed = None
            return {
                "ok": False,
                "status_code": int(getattr(exc, "code", 500)),
                "url": target,
                "error": raw or str(exc),
                "data": parsed,
            }
        except URLError as exc:
            return {"ok": False, "status_code": 0, "url": target, "error": str(exc)}
        except Exception as exc:  # pragma: no cover
            return {"ok": False, "status_code": 0, "url": target, "error": str(exc)}

    def _http_ok(self, url: str) -> dict[str, Any]:
        return self._http_json("GET", url)

    def health_readiness(self) -> dict[str, Any]:
        crm_db_ok = Path(self.crm_db_path).exists()
        mail_db_ok = Path(self.email_db_path).exists()
        crm_api = self._http_ok(f"{self.crm_api_url}/health")
        email_api = self._http_ok(f"{self.email_api_url}/health")
        tool_state = self._tool_state()
        return {
            "mesh_loaded": self.mesh_root.exists(),
            "service_registry_loaded": bool(self.service_registry),
            "api_manifest_loaded": bool(self.api_manifest),
            "manifest_validation_status": self.manifest_validation_status,
            "data_authority_contract": self.data_authority_contract,
            "allowed_tools_count": tool_state["allowed_tools_count"],
            "blocked_tools_count": tool_state["blocked_tools_count"],
            "write_tools_enabled": tool_state["write_tools_enabled"],
            "write_tools_allowed_by_permissions": tool_state["write_tools_allowed_by_permissions"],
            "write_tools_requiring_user_approval": tool_state["write_tools_requiring_user_approval"],
            "crm_db_reachable": crm_db_ok,
            "prime_mail_db_reachable": mail_db_ok,
            "crm_api_reachable": bool(crm_api.get("ok")),
            "prime_mail_api_reachable": bool(email_api.get("ok")),
            "crm_db_path": self.crm_db_path,
            "prime_mail_db_path": self.email_db_path,
            "crm_api": crm_api,
            "prime_mail_api": email_api,
        }

    def _manifest_tools(self) -> dict[str, Any]:
        return self.api_manifest.get("tools", {}) if isinstance(self.api_manifest, dict) else {}

    def _tool_state(self) -> dict[str, int]:
        tools = self._manifest_tools()
        allowed = 0
        blocked = 0
        write_enabled = 0
        write_allowed_by_permissions = 0
        write_requires_approval = 0
        for _name, spec in tools.items():
            if self.is_tool_allowed(_name):
                allowed += 1
                if self._is_write_access_level(str(spec.get("access_level", "read"))):
                    write_enabled += 1
                    write_allowed_by_permissions += 1
                    if bool(spec.get("requires_user_approval")):
                        write_requires_approval += 1
            else:
                blocked += 1
                if self._is_write_access_level(str(spec.get("access_level", "read"))) and bool(spec.get("requires_user_approval")):
                    write_requires_approval += 1
        return {
            "allowed_tools_count": allowed,
            "blocked_tools_count": blocked,
            "write_tools_enabled": write_enabled,
            "write_tools_allowed_by_permissions": write_allowed_by_permissions,
            "write_tools_requiring_user_approval": write_requires_approval,
        }

    def _is_write_access_level(self, access_level: str) -> bool:
        return access_level in {"write_prepare", "write_send", "destructive", "merge", "delete", "stage-change"}

    def _compact_message(self, item: dict[str, Any]) -> dict[str, Any]:
        text = str(item.get("text_body") or "").strip()
        text = re.sub(r"=\r?\n", "", text)
        text = re.sub(r"=([A-Fa-f0-9]{2})", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        return {
            "id": item.get("id"),
            "message_id": item.get("message_id"),
            "sender": item.get("sender"),
            "recipient": item.get("recipient"),
            "subject": item.get("subject"),
            "date": item.get("date"),
            "folder": item.get("folder"),
            "read": item.get("read"),
            "starred": item.get("starred"),
            "has_attachments": item.get("has_attachments"),
            "thread_id": item.get("thread_id"),
            "preview": text[:280],
        }

    def _permission_for_tool(self, tool_name: str) -> bool:
        if self.access_mode == "read_only":
            return False
        mapping = {
            "orb.crm.note.add": self.permission_flags["allow_notes"],
            "orb.crm.activity.add": self.permission_flags["allow_activity_write"],
            "orb.mail.draft.prepare": self.permission_flags["allow_email_drafts"],
            "orb.mail.message.update": self.permission_flags["allow_email_drafts"],
        }
        if tool_name in mapping:
            return bool(mapping[tool_name])
        if "delete" in tool_name:
            return self.permission_flags["allow_contact_delete"]
        if "merge" in tool_name:
            return self.permission_flags["allow_contact_merge"]
        if "stage" in tool_name:
            return self.permission_flags["allow_stage_change"]
        return False

    def is_tool_allowed(self, tool_name: str) -> bool:
        decision = self.authorize_tool(tool_name)
        return bool(decision.get("allowed"))

    def authorize_tool(self, tool_name: str, explicit_user_approval: bool = False) -> dict[str, Any]:
        if not self.manifest_validation_status.get("valid", False):
            spec = self._manifest_tools().get(tool_name, {})
            access_level = str(spec.get("access_level", "read"))
            if self._is_write_access_level(access_level):
                return {"allowed": False, "reason": "manifest_invalid_write_blocked", "tool": tool_name}
        spec = self._manifest_tools().get(tool_name, {})
        if not spec:
            return {"allowed": False, "reason": "tool_not_in_manifest", "tool": tool_name}
        if not bool(spec.get("default_enabled", False)):
            return {"allowed": False, "reason": "tool_disabled_in_manifest", "tool": tool_name}
        tiers = spec.get("allowed_orb_tiers", [])
        if tiers and self.orb_tier not in tiers:
            return {"allowed": False, "reason": "orb_tier_not_allowed", "tool": tool_name}
        if spec.get("blocked_reason"):
            return {"allowed": False, "reason": str(spec.get("blocked_reason")), "tool": tool_name}
        access_level = str(spec.get("access_level", "read"))
        if not self._is_write_access_level(access_level):
            return {"allowed": True, "reason": "allowed_read", "tool": tool_name}
        if access_level in {"destructive", "delete", "merge", "stage-change"}:
            return {"allowed": False, "reason": "destructive_or_stage_change_blocked_by_default", "tool": tool_name}
        if not self._permission_for_tool(tool_name):
            return {"allowed": False, "reason": "permission_flag_disabled", "tool": tool_name}
        if access_level == "write_send":
            if not explicit_user_approval:
                return {"allowed": False, "reason": "explicit_user_approval_required", "tool": tool_name}
            if not self.permission_flags["allow_email_send"]:
                return {"allowed": False, "reason": "email_send_permission_disabled", "tool": tool_name}
        return {"allowed": True, "reason": "allowed_write", "tool": tool_name}

    def list_allowed_tools(self) -> list[str]:
        return [name for name in self._manifest_tools().keys() if self.is_tool_allowed(name)]

    def search_contacts(self, query: str, limit: int = 20) -> dict[str, Any]:
        q = (query or "").strip()
        sql_like = f"%{q.lower()}%"
        with self._connect(self.crm_db_path) as conn:
            rows = conn.execute(
                """
                SELECT id, name, email, phone, crm_stage, lead_source, owner, updated_at
                FROM contacts
                WHERE lower(name) LIKE ? OR lower(email) LIKE ? OR lower(phone) LIKE ?
                ORDER BY datetime(COALESCE(updated_at, created_at, last_contacted_at)) DESC
                LIMIT ?
                """,
                (sql_like, sql_like, sql_like, int(limit)),
            ).fetchall()
        return {"query": q, "count": len(rows), "contacts": [dict(r) for r in rows]}

    def pipeline_status(self) -> dict[str, Any]:
        with self._connect(self.crm_db_path) as conn:
            stage_rows = conn.execute(
                """
                SELECT COALESCE(NULLIF(trim(crm_stage), ''), 'unassigned') AS stage, COUNT(*) AS count
                FROM contacts
                GROUP BY stage
                ORDER BY count DESC
                """
            ).fetchall()
            activity_rows = conn.execute(
                """
                SELECT activity_type, COUNT(*) AS count
                FROM crm_activities
                GROUP BY activity_type
                ORDER BY count DESC
                LIMIT 12
                """
            ).fetchall()
        return {
            "pipeline_stages": [dict(r) for r in stage_rows],
            "activity_summary": [dict(r) for r in activity_rows],
        }

    def inbox_summary(self, limit: int = 25, unread_only: bool = False, account: str | None = None) -> dict[str, Any]:
        result = self._http_json(
            "GET",
            f"{self.email_api_url}/emails",
            params={
                "folder": "inbox",
                "limit": int(limit),
                "offset": 0,
                "unread_only": bool(unread_only),
                "account": account,
            },
        )
        if not result.get("ok"):
            return result
        data = result.get("data") or {}
        emails = data.get("emails", []) if isinstance(data, dict) else []
        compact = [self._compact_message(e) for e in emails]
        unread_count = sum(1 for e in emails if not bool(e.get("read")))
        return {
            "ok": True,
            "limit": int(limit),
            "unread_only": bool(unread_only),
            "account": account,
            "messages": compact,
            "unread_count_in_page": unread_count,
            "source": result.get("url"),
        }

    def search_messages(self, query: str, folder: str | None = None, limit: int = 25) -> dict[str, Any]:
        result = self._http_json(
            "GET",
            f"{self.email_api_url}/emails",
            params={
                "search": query,
                "folder": folder or "inbox",
                "limit": int(limit),
                "offset": 0,
                "search_scope": "all",
            },
        )
        if not result.get("ok"):
            return result
        data = result.get("data") or {}
        emails = data.get("emails", []) if isinstance(data, dict) else []
        compact = [self._compact_message(e) for e in emails]
        return {
            "ok": True,
            "query": query,
            "folder": folder or "inbox",
            "limit": int(limit),
            "count": len(compact),
            "messages": compact,
            "source": result.get("url"),
        }

    def get_message(self, email_id: str) -> dict[str, Any]:
        result = self._http_json("GET", f"{self.email_api_url}/emails/{email_id}")
        if not result.get("ok"):
            return {"found": False, "email_id": email_id, **result}
        return {"found": True, "email_id": email_id, "message": result.get("data"), "source": result.get("url")}

    def create_draft(self, to: str, subject: str, text: str, account: str | None = None) -> dict[str, Any]:
        acct = (account or "default").strip() or "default"
        payload = {"account": acct, "to_addr": to, "subject": subject, "text_body": text, "html_body": ""}
        result = self._http_json("PUT", f"{self.email_api_url}/drafts/{acct}", payload=payload)
        return {"account": acct, "audit_record": {"event": "write_prepare", "tool": "orb.mail.draft.prepare"}, **result}

    def add_crm_note(self, contact_id: str, note: str) -> dict[str, Any]:
        with self._connect(self.crm_db_path) as conn:
            conn.execute(
                """
                INSERT INTO crm_activities (contact_id, activity_type, summary, metadata, created_at)
                VALUES (?, 'note', ?, '{}', datetime('now'))
                """,
                (contact_id, note),
            )
            conn.commit()
        return {"ok": True, "contact_id": contact_id, "activity_type": "note", "audit_record": {"event": "write_prepare", "tool": "orb.crm.note.add"}}

    def add_crm_activity(self, contact_id: str, activity_type: str, summary: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        metadata_json = json.dumps(metadata or {})
        with self._connect(self.crm_db_path) as conn:
            conn.execute(
                """
                INSERT INTO crm_activities (contact_id, activity_type, summary, metadata, created_at)
                VALUES (?, ?, ?, ?, datetime('now'))
                """,
                (contact_id, activity_type, summary, metadata_json),
            )
            conn.commit()
        return {"ok": True, "contact_id": contact_id, "activity_type": activity_type, "audit_record": {"event": "write_prepare", "tool": "orb.crm.activity.add"}}

    def update_message(
        self,
        email_id: str,
        read: bool | None = None,
        starred: bool | None = None,
        archived: bool | None = None,
        folder: str | None = None,
    ) -> dict[str, Any]:
        updates: dict[str, Any] = {}
        if read is not None:
            updates["read"] = bool(read)
        if starred is not None:
            updates["starred"] = bool(starred)
        if archived is not None:
            updates["archived"] = bool(archived)
        if folder is not None:
            updates["folder"] = str(folder)
        if not updates:
            return {"ok": False, "error": "no_updates_provided", "email_id": email_id}
        result = self._http_json("PATCH", f"{self.email_api_url}/emails/{email_id}", payload=updates)
        return {"email_id": email_id, "updates": updates, "audit_record": {"event": "write_prepare", "tool": "orb.mail.message.update"}, **result}

    def unified_snapshot(self) -> dict[str, Any]:
        with self._connect(self.crm_db_path) as crm_conn:
            contact_count = crm_conn.execute("SELECT COUNT(*) AS count FROM contacts").fetchone()["count"]
            activity_count = crm_conn.execute("SELECT COUNT(*) AS count FROM crm_activities").fetchone()["count"]
        inbox = self.inbox_summary(limit=10, unread_only=False, account=None)
        health = self.health_readiness()
        return {
            "crm": {"contacts_total": int(contact_count), "activities_total": int(activity_count)},
            "mail": {
                "recent_messages": inbox.get("messages", []),
                "unread_count_in_page": inbox.get("unread_count_in_page", 0),
                "source": inbox.get("source"),
            },
            "health": health,
        }
