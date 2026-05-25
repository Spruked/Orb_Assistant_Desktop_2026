from pathlib import Path
from .cognitive_state import IntuitiveCognition


class IntuitiveEngine:
    def __init__(self, worker_root: Path):
        self.root = worker_root
        self.vault_path = worker_root / "vault"
        self.cognition = IntuitiveCognition(self.vault_path)

    def check_necessity(self, current_node, field_map):
        # Placeholder
        return {"necessity": False}

    # Integration
    def advise_orb(self, hlsf_data: Dict) -> Dict:
        field_map = hlsf_data.get("field_map", {})
        current_node = hlsf_data.get("current_node")

        necessity = self.check_necessity(current_node, field_map)

        if necessity["necessity"]:
            verdict_id = self.cognition.record_necessity_verdict(necessity, hlsf_data)

            # Weight by apriori validation if available
            cond_hash = f"d{necessity['density']}_s{int(necessity['symmetry']*100)}"
            if cond_hash in self.cognition.apriori_necessities:
                ap = self.cognition.apriori_necessities[cond_hash]
                bonus_weight = min(0.1, ap.validation_count * 0.01)
                base_weight = 0.35
            else:
                bonus_weight = 0
                base_weight = 0.35

            return {
                "advisory_type": "intuitive",
                "verdict_id": verdict_id,
                "verdict": "substance_unity_achieved",
                "conclusion": "jump_necessary",
                "certainty": necessity["certainty"],
                "unity_vector": necessity["vector"],
                "ethics_alignment": necessity.get("unity_score", 0),
                "deterministic": True,
                "weight": (necessity["certainty"] * base_weight) + bonus_weight,
                "apriori_validated": cond_hash in self.cognition.apriori_necessities,
            }

        return {
            "advisory_type": "intuitive",
            "verdict_id": None,
            "verdict": "field_dispersed",
            "certainty": 0.0,
            "weight": 0.0,
        }

    def validate_verdict(self, verdict_id: str, was_optimal: bool):
        self.cognition.validate_necessity(verdict_id, was_optimal)

    def process_idle(self):
        return self.cognition.idle_recursive_process()
