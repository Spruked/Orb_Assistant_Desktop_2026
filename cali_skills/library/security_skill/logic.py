import base64
import hashlib
import hmac
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

try:
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
except Exception:
    default_backend = None
    hashes = None
    ChaCha20Poly1305 = None
    PBKDF2HMAC = None

from cali_skills.core.interface import CALISkill


class SecuritySkill(CALISkill):
    """Cryptographic operations and local vault management."""

    def __init__(self, skill_id: str, config: Dict[str, Any]):
        super().__init__(skill_id, config)
        self.vault_path = Path(__file__).resolve().parent / "vault"
        self.vault_path.mkdir(parents=True, exist_ok=True)

    def _load_metadata(self) -> Dict[str, Any]:
        return self.config

    def can_handle(self, intent: str, context: Dict[str, Any]) -> float:
        intent_lower = str(intent or "").lower()
        if any(trigger in intent_lower for trigger in self.config.get("triggers", [])):
            return 0.95
        if context.get("requires_encryption") or context.get("vault_operation"):
            return 0.9
        return 0.05

    def execute(self, command: str, params: Dict[str, Any], memory: Any) -> Dict[str, Any]:
        try:
            dispatch = {
                "chacha20_encrypt": self._chacha20_encrypt,
                "chacha20_decrypt": self._chacha20_decrypt,
                "sha256_hash": self._sha256_hash,
                "sha256": self._sha256_hash,
                "hmac_sign": self._hmac_sign,
                "verify_integrity": self._verify_integrity,
                "file_verify": self._verify_integrity,
                "generate_key": self._generate_key,
                "vault_store": self._vault_store,
                "vault_retrieve": self._vault_retrieve,
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

    def _require_crypto(self) -> Dict[str, Any] | None:
        if ChaCha20Poly1305 is None:
            return {"status": "missing_dependency", "error": "cryptography is not installed", "confidence": 1.0}
        return None

    def _derive_key(self, params: Dict[str, Any]) -> tuple[bytes, str | None]:
        key = params.get("key")
        password = params.get("password")
        if password and not key:
            salt = os.urandom(16)
            kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=480000, backend=default_backend())
            return kdf.derive(str(password).encode("utf-8")), base64.b64encode(salt).decode()
        if isinstance(key, str):
            try:
                raw = base64.b64decode(key)
                if raw:
                    key = raw
            except Exception:
                key = key.encode("utf-8")
        key = key or os.urandom(32)
        return bytes(key[:32]).ljust(32, b"\0"), None

    def _chacha20_encrypt(self, params: Dict[str, Any]) -> Dict[str, Any]:
        missing = self._require_crypto()
        if missing:
            return missing
        data = params.get("data", b"")
        plaintext = data.encode("utf-8") if isinstance(data, str) else bytes(data)
        if not plaintext:
            return {"status": "error", "error": "No data provided", "confidence": 1.0}
        if not params.get("key") and not params.get("password"):
            return {"status": "needs_configuration", "error": "key or password required for reversible encryption", "confidence": 1.0}
        key, salt_b64 = self._derive_key(params)
        nonce = os.urandom(12)
        associated_data = params.get("associated_data", b"")
        associated_data = associated_data.encode("utf-8") if isinstance(associated_data, str) else associated_data
        ciphertext = ChaCha20Poly1305(key).encrypt(nonce, plaintext, associated_data)
        result = {
            "status": "success",
            "ciphertext": base64.b64encode(ciphertext).decode(),
            "nonce": base64.b64encode(nonce).decode(),
            "algorithm": "ChaCha20-Poly1305",
            "confidence": 0.99,
        }
        if salt_b64:
            result["salt"] = salt_b64
            result["kdf"] = "PBKDF2-SHA256"
        if associated_data:
            result["associated_data_included"] = True
        return result

    def _chacha20_decrypt(self, params: Dict[str, Any]) -> Dict[str, Any]:
        missing = self._require_crypto()
        if missing:
            return missing
        ciphertext = base64.b64decode(params.get("ciphertext"))
        nonce = base64.b64decode(params.get("nonce"))
        password = params.get("password")
        key = params.get("key")
        salt = base64.b64decode(params.get("salt")) if params.get("salt") else None
        if password and not key:
            if not salt:
                return {"status": "error", "error": "Salt required for password decryption", "confidence": 1.0}
            kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=480000, backend=default_backend())
            key = kdf.derive(str(password).encode("utf-8"))
        elif isinstance(key, str):
            try:
                key = base64.b64decode(key)
            except Exception:
                key = key.encode("utf-8")
        key = bytes((key or b"")[:32]).ljust(32, b"\0")
        associated_data = params.get("associated_data", b"")
        associated_data = associated_data.encode("utf-8") if isinstance(associated_data, str) else associated_data
        plaintext = ChaCha20Poly1305(key).decrypt(nonce, ciphertext, associated_data)
        try:
            return {"status": "success", "data": plaintext.decode("utf-8"), "format": "string", "confidence": 0.99}
        except UnicodeDecodeError:
            return {"status": "success", "data": base64.b64encode(plaintext).decode(), "format": "base64", "confidence": 0.99}

    def _sha256_hash(self, params: Dict[str, Any]) -> Dict[str, Any]:
        file_path = params.get("file") or params.get("path")
        if file_path:
            h = hashlib.sha256()
            path = Path(file_path).expanduser()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(8192), b""):
                    h.update(chunk)
            return {"status": "success", "hash": h.hexdigest(), "algorithm": "SHA-256", "source": str(path), "confidence": 1.0}
        data = params.get("data", params.get("text", ""))
        data = data.encode("utf-8") if isinstance(data, str) else bytes(data)
        if not data:
            return {"status": "error", "error": "No data or file provided", "confidence": 1.0}
        return {"status": "success", "hash": hashlib.sha256(data).hexdigest(), "algorithm": "SHA-256", "source": "data", "confidence": 1.0}

    def _hmac_sign(self, params: Dict[str, Any]) -> Dict[str, Any]:
        data = params.get("data", b"")
        key = params.get("key", b"")
        data = data.encode("utf-8") if isinstance(data, str) else bytes(data)
        key = key.encode("utf-8") if isinstance(key, str) else bytes(key)
        if not data or not key:
            return {"status": "error", "error": "Data and key required", "confidence": 1.0}
        return {"status": "success", "signature": hmac.new(key, data, hashlib.sha256).hexdigest(), "algorithm": "HMAC-SHA256", "confidence": 0.99}

    def _verify_integrity(self, params: Dict[str, Any]) -> Dict[str, Any]:
        path = Path(params.get("file") or params.get("path")).expanduser()
        expected_hash = params.get("expected_hash")
        result = self._sha256_hash({"file": str(path)})
        if result.get("status") != "success" or not expected_hash:
            return result
        return {"status": "success", "valid": hmac.compare_digest(result["hash"], expected_hash), "expected": expected_hash, "actual": result["hash"], "confidence": 1.0}

    def _generate_key(self, params: Dict[str, Any]) -> Dict[str, Any]:
        key_type = params.get("type", "chacha20")
        length = {"chacha20": 32, "aes256": 32, "aes128": 16}.get(key_type, int(params.get("length", 32)))
        key = os.urandom(length)
        fingerprint = hashlib.sha256(key).hexdigest()
        key_id = str(params.get("key_id") or f"{key_type}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{fingerprint[:12]}")
        vault_password = params.get("vault_password")
        if not vault_password:
            return {
                "status": "needs_configuration",
                "error": "vault_password required to store generated key",
                "key_id": key_id,
                "length": length,
                "algorithm": key_type,
                "fingerprint": fingerprint[:16],
                "confidence": 1.0,
            }
        stored = self._vault_store({
            "key_id": key_id,
            "data": {
                "key": base64.b64encode(key).decode(),
                "algorithm": key_type,
                "length": length,
                "fingerprint": fingerprint,
                "created_at": datetime.utcnow().isoformat(),
            },
            "encrypt": True,
            "vault_password": vault_password,
        })
        if stored.get("status") != "success":
            return stored
        return {
            "status": "success",
            "key_id": key_id,
            "stored": True,
            "length": length,
            "algorithm": key_type,
            "fingerprint": fingerprint[:16],
            "confidence": 0.99,
        }

    def _vault_store(self, params: Dict[str, Any]) -> Dict[str, Any]:
        key_id = str(params.get("key_id") or "").strip()
        if not key_id:
            return {"status": "error", "error": "key_id required", "confidence": 1.0}
        vault_file = self.vault_path / f"{key_id}.vault"
        data = params.get("data")
        if params.get("encrypt", True):
            enc = self._chacha20_encrypt({"data": json.dumps(data), "password": params.get("vault_password")})
            if enc["status"] != "success":
                return enc
            storage_data = {"encrypted": True, "payload": enc["ciphertext"], "nonce": enc["nonce"], "salt": enc.get("salt"), "stored_at": datetime.utcnow().isoformat()}
        else:
            storage_data = {"encrypted": False, "payload": data, "stored_at": datetime.utcnow().isoformat()}
        vault_file.write_text(json.dumps(storage_data, indent=2), encoding="utf-8")
        return {"status": "success", "key_id": key_id, "encrypted": storage_data["encrypted"], "path": str(vault_file), "confidence": 0.99}

    def _vault_retrieve(self, params: Dict[str, Any]) -> Dict[str, Any]:
        key_id = str(params.get("key_id") or "").strip()
        vault_file = self.vault_path / f"{key_id}.vault"
        if not vault_file.exists():
            return {"status": "error", "error": f"Key not found: {key_id}", "confidence": 1.0}
        storage_data = json.loads(vault_file.read_text(encoding="utf-8"))
        if storage_data.get("encrypted"):
            dec = self._chacha20_decrypt({"ciphertext": storage_data["payload"], "nonce": storage_data["nonce"], "salt": storage_data.get("salt"), "password": params.get("vault_password")})
            if dec["status"] != "success":
                return dec
            return {"status": "success", "data": json.loads(dec["data"]), "decrypted": True, "stored_at": storage_data.get("stored_at"), "confidence": 0.99}
        return {"status": "success", "data": storage_data["payload"], "decrypted": False, "stored_at": storage_data.get("stored_at"), "confidence": 0.99}

    def get_memory_scope(self) -> List[str]:
        return ["skills/security", "vault_keys", "certificates", "audit_logs"]
