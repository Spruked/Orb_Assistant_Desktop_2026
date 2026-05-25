import base64
import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from cali_skills.core.interface import CALISkill


@dataclass
class NFTMetadata:
    name: str
    description: str
    image: str
    attributes: List[Dict[str, Any]]
    creator: str
    created_at: str
    certificate_type: str
    encryption_hash: Optional[str] = None
    forensic_signature: Optional[str] = None


class TrueMarkSkill(CALISkill):
    """TrueMark Mint Engine for certificate and NFT preparation."""

    def __init__(self, skill_id: str, config: Dict[str, Any]):
        super().__init__(skill_id, config)
        self.staging_path = Path(__file__).resolve().parent / "staging"
        self.staging_path.mkdir(parents=True, exist_ok=True)
        self.cert_templates = Path(__file__).resolve().parent / "templates"
        self.runtime_context: Dict[str, Any] = {}

    def _load_metadata(self) -> Dict[str, Any]:
        return self.config

    def can_handle(self, intent: str, context: Dict[str, Any]) -> float:
        intent_lower = str(intent or "").lower()
        if any(token in intent_lower for token in ["k-nft", "knft", "h-nft", "hnft", "l-nft", "lnft", "c-nft", "cnft"]):
            return 0.98
        if any(trigger in intent_lower for trigger in self.config.get("triggers", [])):
            return 0.95
        return 0.9 if context.get("operation") in ["mint", "certificate", "blockchain"] else 0.05

    def execute(self, command: str, params: Dict[str, Any], memory: Any) -> Dict[str, Any]:
        try:
            self.runtime_context = memory if isinstance(memory, dict) else {}
            dispatch = {
                "prepare_knft": self._prepare_knft,
                "prepare_hnft": self._prepare_hnft,
                "prepare_lnft": self._prepare_lnft,
                "prepare_cnft": self._prepare_cnft,
                "generate_metadata": self._generate_metadata,
                "create_forensic_cert": self._create_forensic_cert,
                "validate_certificate": self._validate_certificate,
                "encrypt_assets": self._encrypt_assets,
                "prepare_arweave_bundle": self._prepare_arweave_bundle,
                "estimate_minting_cost": self._estimate_minting_cost,
                "explain": self._explain,
                "start_service": self._start_service,
            }
            handler = dispatch.get(command)
            if not handler:
                return {"status": "error", "error": f"Unknown command: {command}", "confidence": 1.0}
            return handler(params or {})
        except Exception as exc:
            return {"status": "error", "error": str(exc), "command": command, "timestamp": datetime.utcnow().isoformat(), "confidence": 1.0}

    def _core_path(self) -> Path:
        return Path(__file__).resolve().parents[3] / "CALI_System" / "core_knowledge" / "truemark_mint"

    def _explain(self, params: Dict[str, Any]) -> Dict[str, Any]:
        overview_path = self._core_path() / "overview.txt"
        overview = overview_path.read_text(encoding="utf-8", errors="replace").strip() if overview_path.exists() else "TrueMark Mint prepares local-first certificate and NFT workflows."
        return {"status": "success", "result": overview, "confidence": 0.9}

    def _start_service(self, params: Dict[str, Any]) -> Dict[str, Any]:
        launch_path = self._core_path() / "launch.json"
        launch = json.loads(launch_path.read_text(encoding="utf-8")) if launch_path.exists() else {}
        cmd = str(launch.get("command") or "").strip()
        if not cmd:
            return {"status": "needs_configuration", "error": "TrueMark launch command is not configured.", "confidence": 1.0}
        subprocess.Popen(cmd, shell=True, cwd=launch.get("cwd") or None)
        return {"status": "success", "result": "TrueMark service start requested.", "confidence": 0.9}

    def _save_metadata(self, prefix: str, metadata: NFTMetadata) -> Dict[str, Any]:
        staging_id = f"{prefix}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{hashlib.md5(metadata.name.encode()).hexdigest()[:8]}"
        staging_file = self.staging_path / f"{staging_id}.json"
        staging_file.write_text(json.dumps(asdict(metadata), indent=2), encoding="utf-8")
        return {"staging_id": staging_id, "staging_path": str(staging_file), "metadata": asdict(metadata)}

    def _prepare_knft(self, params: Dict[str, Any]) -> Dict[str, Any]:
        title = params.get("title", "Untitled Knowledge")
        metadata = NFTMetadata(
            name=title,
            description=f"Knowledge NFT: {title}",
            image=params.get("cover_image", ""),
            attributes=[
                {"trait_type": "Type", "value": "K-NFT"},
                {"trait_type": "Subject", "value": params.get("subject", "General")},
                {"trait_type": "Level", "value": params.get("level", "Intermediate")},
                {"trait_type": "Verified", "value": "True"},
            ],
            creator=params.get("creator", "unknown"),
            created_at=datetime.utcnow().isoformat(),
            certificate_type="K-NFT",
        )
        if params.get("encrypt", True):
            security = self._get_security_skill()
            if security is None:
                return {"status": "needs_dependency", "error": "Security skill must be supplied through runtime context.", "confidence": 1.0}
            enc = security.execute("chacha20_encrypt", {"data": json.dumps(params.get("knowledge_data", {})), "password": params.get("encryption_key") or params.get("password")}, self.runtime_context)
            if enc.get("status") == "success":
                metadata.encryption_hash = hashlib.sha256(enc["ciphertext"].encode()).hexdigest()[:16]
            else:
                return {
                    "status": enc.get("status", "error"),
                    "error": enc.get("error", "K-NFT encryption failed"),
                    "nft_type": "K-NFT",
                    "confidence": 1.0,
                }
        saved = self._save_metadata("knft", metadata)
        return {"status": "success", "nft_type": "K-NFT", **saved, "next_steps": ["encrypt_assets", "prepare_arweave_bundle", "estimate_minting_cost"], "confidence": 0.97}

    def _prepare_hnft(self, params: Dict[str, Any]) -> Dict[str, Any]:
        forensic = self._create_forensic_cert({"data": params.get("historical_data"), "timestamp": params.get("event_date", datetime.utcnow().isoformat()), "witnesses": params.get("witnesses", [])})
        metadata = NFTMetadata(
            name=f"Historical Record: {params.get('title', 'Untitled')}",
            description=params.get("description", "Historical timestamp record"),
            image=params.get("evidence_image", ""),
            attributes=[
                {"trait_type": "Type", "value": "H-NFT"},
                {"trait_type": "EventDate", "value": params.get("event_date", datetime.utcnow().isoformat())},
                {"trait_type": "Category", "value": params.get("category", "Document")},
                {"trait_type": "Immutable", "value": "True"},
            ],
            creator=params.get("creator", "unknown"),
            created_at=datetime.utcnow().isoformat(),
            certificate_type="H-NFT",
            forensic_signature=forensic.get("signature"),
        )
        return {"status": "success", "nft_type": "H-NFT", "forensic_cert": forensic.get("signature"), **self._save_metadata("hnft", metadata), "confidence": 0.97}

    def _prepare_lnft(self, params: Dict[str, Any]) -> Dict[str, Any]:
        terms = params.get("license_terms", {})
        metadata = NFTMetadata(
            name=f"License: {params.get('asset_name', 'Untitled')}",
            description=terms.get("description", "Digital License Token"),
            image=params.get("asset_image", ""),
            attributes=[
                {"trait_type": "Type", "value": "L-NFT"},
                {"trait_type": "LicenseType", "value": terms.get("type", "Standard")},
                {"trait_type": "Duration", "value": terms.get("duration", "Perpetual")},
                {"trait_type": "Transferable", "value": str(terms.get("transferable", True))},
                {"trait_type": "CommercialUse", "value": str(terms.get("commercial", False))},
            ],
            creator=params.get("licensor", "unknown"),
            created_at=datetime.utcnow().isoformat(),
            certificate_type="L-NFT",
        )
        return {"status": "success", "nft_type": "L-NFT", "license_terms": terms, **self._save_metadata("lnft", metadata), "confidence": 0.97}

    def _prepare_cnft(self, params: Dict[str, Any]) -> Dict[str, Any]:
        recipient = params.get("recipient", {})
        issuer = params.get("issuer", {})
        achievement = params.get("achievement", {})
        metadata = NFTMetadata(
            name=f"Certificate: {achievement.get('title', 'Certification')}",
            description=f"Awarded to {recipient.get('name', 'Unknown')} for {achievement.get('description', 'achievement')}",
            image=params.get("certificate_design", ""),
            attributes=[
                {"trait_type": "Type", "value": "C-NFT"},
                {"trait_type": "Recipient", "value": recipient.get("name", "Unknown")},
                {"trait_type": "Issuer", "value": issuer.get("name", "Unknown")},
                {"trait_type": "IssueDate", "value": achievement.get("date", datetime.utcnow().isoformat())},
                {"trait_type": "CredentialID", "value": achievement.get("credential_id", "N/A")},
                {"trait_type": "ValidUntil", "value": achievement.get("expiry", "Never")},
            ],
            creator=issuer.get("name", "unknown"),
            created_at=datetime.utcnow().isoformat(),
            certificate_type="C-NFT",
        )
        return {"status": "success", "nft_type": "C-NFT", "recipient": recipient, **self._save_metadata("cnft", metadata), "confidence": 0.98}

    def _generate_metadata(self, params: Dict[str, Any]) -> Dict[str, Any]:
        nft_type = str(params.get("nft_type") or "K-NFT").upper().replace("_", "-")
        return {"K-NFT": self._prepare_knft, "H-NFT": self._prepare_hnft, "L-NFT": self._prepare_lnft, "C-NFT": self._prepare_cnft}.get(nft_type, self._prepare_knft)(params)

    def _create_forensic_cert(self, params: Dict[str, Any]) -> Dict[str, Any]:
        data_hash = hashlib.sha256(json.dumps(params.get("data", ""), sort_keys=True, default=str).encode()).hexdigest()
        timestamp = params.get("timestamp", datetime.utcnow().isoformat())
        timestamp_hash = hashlib.sha256(f"{data_hash}:{timestamp}".encode()).hexdigest()
        witness_hashes = [hashlib.sha256(str(w).encode()).hexdigest()[:16] for w in params.get("witnesses", [])]
        signature = hashlib.sha256(f"{timestamp_hash}:{':'.join(witness_hashes)}".encode()).hexdigest()
        cert = {"data_hash": data_hash, "timestamp": timestamp, "signature": signature, "witness_count": len(witness_hashes), "algorithm": "SHA-256", "standard": "TrueMark-Forensic-v2"}
        return {"status": "success", "certificate": cert, "signature": signature, "confidence": 0.99}

    def _validate_certificate(self, params: Dict[str, Any]) -> Dict[str, Any]:
        cert = params.get("certificate", {})
        expected_hash = hashlib.sha256(json.dumps(params.get("original_data", ""), sort_keys=True, default=str).encode()).hexdigest()
        return {"status": "success", "valid": cert.get("data_hash") == expected_hash, "expected_hash": expected_hash, "stored_hash": cert.get("data_hash"), "confidence": 0.99}

    def _encrypt_assets(self, params: Dict[str, Any]) -> Dict[str, Any]:
        file_path = Path(params.get("file", "")).expanduser()
        data = file_path.read_bytes()
        security = self._get_security_skill()
        if security is None:
            return {"status": "needs_dependency", "error": "Security skill must be supplied through runtime context.", "confidence": 1.0}
        enc = security.execute("chacha20_encrypt", {"data": base64.b64encode(data).decode(), "key": params.get("key"), "password": params.get("password")}, self.runtime_context)
        if enc.get("status") != "success":
            return enc
        enc_path = Path(str(file_path) + ".enc")
        enc_path.write_text(json.dumps(enc, indent=2), encoding="utf-8")
        return {"status": "success", "encrypted_file": str(enc_path), "original_hash": hashlib.sha256(data).hexdigest(), "encryption": "ChaCha20-Poly1305", "confidence": 0.99}

    def _prepare_arweave_bundle(self, params: Dict[str, Any]) -> Dict[str, Any]:
        staging_file = self.staging_path / f"{params.get('staging_id')}.json"
        if not staging_file.exists():
            return {"status": "error", "error": f"Staging ID not found: {params.get('staging_id')}", "confidence": 1.0}
        metadata = json.loads(staging_file.read_text(encoding="utf-8"))
        tags = {"Content-Type": "application/json", "App-Name": "TrueMark-Mint", "App-Version": "2.0", "NFT-Type": metadata.get("certificate_type", "Unknown"), "Creator": metadata.get("creator", "Unknown"), "Timestamp": metadata.get("created_at")}
        bundle = {"data": metadata, "tags": tags, "target": params.get("target_wallet"), "quantity": "0", "reward": params.get("reward", "auto")}
        return {"status": "success", "bundle": bundle, "ready_for_upload": True, "estimated_size": len(json.dumps(bundle)), "confidence": 0.96}

    def _estimate_minting_cost(self, params: Dict[str, Any]) -> Dict[str, Any]:
        chain = params.get("chain", "polygon")
        file_size = float(params.get("file_size", 5000))
        gas_cost = 0.001 if chain == "polygon" and params.get("nft_type", "K-NFT") == "K-NFT" else (0.002 if chain == "polygon" else 0.005)
        storage_cost = (file_size / 1024) * 0.0001 if chain == "polygon" else 0
        return {"status": "success", "chain": chain, "gas_cost": gas_cost, "storage_cost": storage_cost, "total_estimate": gas_cost + storage_cost, "currency": "MATIC" if chain == "polygon" else "ETH", "confidence": 0.85}

    def _get_security_skill(self):
        skills = self.runtime_context.get("skills", {}) if isinstance(self.runtime_context, dict) else {}
        security = skills.get("security")
        if security and hasattr(security, "execute"):
            return security
        return None

    def get_memory_scope(self) -> List[str]:
        return ["skills/truemark", "minting_history", "certificate_registry"]
