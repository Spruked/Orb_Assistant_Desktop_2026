#!/usr/bin/env python3
"""Final validation layer - called right before user delivery.

FROZEN INTERFACE v1.0.0-final
============================
This validation pipeline is OBSERVATIONAL ONLY.

Core logic MUST NOT import validation logic.
Core logic MUST ONLY emit verdicts TO this pipeline for witnessing.

The FinalValidationLayer.validate_for_delivery() is the ONLY entry point.
Any changes to this interface require full system validation.
"""

import json
import sys
import time
import hashlib
from pathlib import Path
from typing import Dict

# Import all three validators
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir / "deductive_validator"))
sys.path.insert(0, str(current_dir / "inductive_validator"))
sys.path.insert(0, str(current_dir / "intuitive_validator"))

from deductive_validator.logic.deductive_validation import DeductiveValidator
from inductive_validator.logic.inductive_validation import InductiveValidator
from intuitive_validator.logic.intuitive_validation import IntuitiveValidator


class FinalValidationLayer:
    """
    Non-blocking validation witness before user return.

    FROZEN INTERFACE v1.0.0-final
    =============================
    This is the FINAL OBSERVATIONAL LAYER.

    - Core logic calls validate_for_delivery() ONLY
    - Original verdicts are NEVER modified
    - All observations are recorded for audit
    - Signed envelopes provide tamper-evident provenance
    """

    def __init__(self):
        self.deductive = DeductiveValidator(Path("deductive_validator"))
        self.inductive = InductiveValidator(Path("inductive_validator"))
        self.intuitive = IntuitiveValidator(Path("intuitive_validator"))

    def create_signed_witness_envelope(self, validation_record: Dict) -> Dict:
        """
        Create a tamper-evident signed envelope containing all validator observations.
        Provides cryptographic provenance of what the system believed at delivery time.
        """
        # Extract the core content to be signed
        envelope_content = {
            "delivery_timestamp": validation_record["delivery_timestamp"],
            "original_verdict_hash": hashlib.sha256(
                json.dumps(
                    validation_record["original_verdict"], sort_keys=True
                ).encode()
            ).hexdigest()[:16],
            "validator_observations": {
                "deductive": {
                    "observation_id": validation_record["witness_validations"][
                        "deductive"
                    ]["observation_id"],
                    "check_status": validation_record["witness_validations"][
                        "deductive"
                    ]["check_status"],
                    "parallel_confidence": validation_record["witness_validations"][
                        "deductive"
                    ]["parallel_confidence"],
                    "alignment": validation_record["witness_validations"]["deductive"][
                        "alignment"
                    ],
                },
                "inductive": {
                    "validation_id": validation_record["witness_validations"][
                        "inductive"
                    ]["validation_id"],
                    "historical_support": validation_record["witness_validations"][
                        "inductive"
                    ]["historical_support"],
                    "alignment": validation_record["witness_validations"]["inductive"][
                        "alignment"
                    ],
                },
                "intuitive": {
                    "validation_id": validation_record["witness_validations"][
                        "intuitive"
                    ]["validation_id"],
                    "symmetry_calculated": validation_record["witness_validations"][
                        "intuitive"
                    ]["symmetry_calculated"],
                    "geometry_validated": validation_record["witness_validations"][
                        "intuitive"
                    ]["geometry_validated"],
                },
            },
            "consensus_analysis": validation_record["consensus_analysis"],
        }

        # Create content hash
        content_str = json.dumps(envelope_content, sort_keys=True)
        content_hash = hashlib.sha256(content_str.encode()).hexdigest()

        # Create deterministic "signature" (in production, this would be cryptographic)
        # Using a combination of content hash + timestamp + system identifier
        signature_seed = f"{content_hash}{validation_record['delivery_timestamp']}SF-ORB_VALIDATION_LAYER"
        signature = hashlib.sha256(signature_seed.encode()).hexdigest()

        # Create the signed envelope
        signed_envelope = {
            "envelope_id": f"env_{int(validation_record['delivery_timestamp'] * 1000)}",
            "content_hash": content_hash,
            "signature": signature,
            "signed_content": envelope_content,
            "signing_authority": "SF-ORB_Final_Validation_Layer",
            "signature_method": "SHA256_deterministic",
            "tamper_evidence": {
                "content_length": len(content_str),
                "validator_count": 3,
                "consensus_congruent": envelope_content["consensus_analysis"][
                    "congruent"
                ],
            },
        }

        return signed_envelope

    def validate_for_delivery(self, core_verdict: Dict, context: Dict) -> Dict:
        """
        Final check before user sees result.
        Documents everything, changes nothing.
        """
        # Package for validators
        package = {
            "verdict": core_verdict,
            "context": context,
            "timestamp": time.time(),
        }

        # Run all three validations (parallel in production)
        ded_val = self.deductive.validate_verdict(package)
        ind_val = self.inductive.validate_verdict(package)

        # Intuitive needs HLSF context
        package["hlsf_context"] = context.get("hlsf", {})
        int_val = self.intuitive.validate_verdict(package)

        # Compile validation record
        validation_record = {
            "delivery_timestamp": time.time(),
            "original_verdict": core_verdict,
            "witness_validations": {
                "deductive": ded_val["validation_layer"],
                "inductive": ind_val["validation_layer"],
                "intuitive": int_val["validation_layer"],
            },
            "consensus_analysis": self._analyze_consensus(
                [
                    ded_val["validation_layer"],
                    ind_val["validation_layer"],
                    int_val["validation_layer"],
                ]
            ),
            "delivery_status": "delivered_with_validation",
            "user_message": "Original verdict preserved with validation witness",
        }

        # Create signed witness envelope
        signed_envelope = self.create_signed_witness_envelope(validation_record)
        validation_record["signed_witness_envelope"] = signed_envelope

        # Log complete record
        with open("final_validation_log.jsonl", "a") as f:
            f.write(json.dumps(validation_record) + "\n")

        # Return original verdict + validation metadata
        # IMPORTANT: Original verdict is unchanged, just documented alongside
        return {
            **core_verdict,  # Original untouched
            "_validation_witness": {
                "checked": True,
                "validators": ["deductive", "inductive", "intuitive"],
                "record_id": validation_record["delivery_timestamp"],
                "congruent": validation_record["consensus_analysis"]["congruent"],
                "signed_envelope_id": signed_envelope["envelope_id"],
                "content_hash": signed_envelope["content_hash"],
            },
        }

    def _analyze_consensus(self, validations: list) -> Dict:
        """Check if validators agree with original."""
        congruent_count = sum(
            1
            for v in validations
            if v.get("alignment") in ["congruent", "supported", "geometry_validated"]
        )
        return {
            "congruent": congruent_count >= 2,
            "agreement_ratio": congruent_count / len(validations),
            "observed_discrepancies": [
                v
                for v in validations
                if v.get("alignment")
                not in ["congruent", "supported", "geometry_validated", None]
            ],
        }


# Usage in UCM Core before return:
# final_layer = FinalValidationLayer()
# user_result = final_layer.validate_for_delivery(core_4_verdict, context)
