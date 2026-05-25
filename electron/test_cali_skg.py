#!/usr/bin/env python3
"""Targeted tests for the CALI SKG subsystem."""

import json
import sys
from pathlib import Path

import pytest


SRC_ROOT = Path(__file__).resolve().parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from cali_skg import CALISKG  # noqa: E402


def test_reason_persists_experience(tmp_path):
    cali = CALISKG(tmp_path)

    result = cali.reason("cause and effect")

    assert result["voice_ready"] is True
    assert "recommended_response" in result
    assert result["advisory_verdict"]["confidence"] >= 0

    status = cali.get_status()
    assert status["a_posteriori_entries"] == 1

    vault_path = tmp_path / "CALI_System" / "memory" / "a_posteriori" / "vault.jsonl"
    assert vault_path.exists()
    assert vault_path.read_text(encoding="utf-8").strip()

    cali.close()


def test_speak_writes_voice_metadata(tmp_path):
    cali = CALISKG(tmp_path)

    package = cali.speak("Testing CALI voice package", emotion="analytical")

    metadata_path = Path(package["output_path"]).with_suffix(".json")
    assert metadata_path.exists()

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["text"] == "Testing CALI voice package"
    assert metadata["voice_config"]["emotion"] == "precise_clear"

    cali.close()


@pytest.mark.asyncio
async def test_research_uses_configured_registry(tmp_path):
    registry_path = tmp_path / "CALI_System" / "config"
    registry_path.mkdir(parents=True, exist_ok=True)
    (registry_path / "api_registry.json").write_text(
        json.dumps(
            {
                "academic": [
                    {
                        "name": "SemanticScholar",
                        "endpoint": "https://example.com/api",
                        "domain": "papers",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    cali = CALISKG(tmp_path)

    async def fake_request(url, params=None, headers=None):
        return {"title": "Synthetic research finding"}

    cali.swarm._request_data = fake_request

    result = await cali.research("reasoning systems", ["academic"])

    assert result["research_synthesis"]["successful_returns"] == 1
    assert "SemanticScholar" in result["voice_response"]

    await cali.aclose()
