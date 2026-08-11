from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = json.loads((ROOT / "machine" / "excellence-state.json").read_text(encoding="utf-8"))
POSITION = json.loads((ROOT / "machine" / "canonical-position.json").read_text(encoding="utf-8"))
CONTRACT = json.loads((ROOT / "machine" / "target-contract.json").read_text(encoding="utf-8"))
RECEIPT = json.loads(
    (
        ROOT
        / "machine"
        / "evolution-receipts"
        / "2026-08-11-multi-tier-dissent-recovery.json"
    ).read_text(encoding="utf-8")
)


class EvolutionReceiptContractTests(unittest.TestCase):
    def test_consumed_cursor_is_bound_to_exact_green_candidate(self):
        self.assertEqual(
            RECEIPT["consumed_cursor"],
            "next:multi_tier_dissent_recovery_and_cross_sensor_clustering",
        )
        self.assertEqual(
            RECEIPT["candidate_source_sha"],
            "fccbf6570728716e607c5ce0ab8768bb5f3f34cf",
        )
        self.assertEqual(RECEIPT["workflow_run"], 31452722206)
        self.assertEqual(RECEIPT["proof"], {"python": "PASS", "go": "PASS"})

    def test_next_cursor_advances_in_all_machine_surfaces(self):
        expected = (
            "next:signature_verified_sensor_identity_cluster_persistence_"
            "and_recovery_receipt_chain"
        )
        self.assertEqual(STATE["evolution_cursor"], expected)
        self.assertEqual(POSITION["next_evolution_cursor"], expected)
        self.assertEqual(CONTRACT["target"]["next_cursor"], expected)
        self.assertEqual(RECEIPT["next_cursor"], expected)

    def test_signature_authentication_remains_a_nonclaim(self):
        position_nonclaims = " ".join(POSITION["nonclaims"]).lower()
        contract_nonclaims = " ".join(CONTRACT["nonclaims"]).lower()
        truth = " ".join(RECEIPT["truth_boundaries"]).lower()
        self.assertIn("signature authenticity", position_nonclaims)
        self.assertIn("cryptographic verification", contract_nonclaims)
        self.assertIn("not verified", truth)

    def test_completed_evolution_preserves_repository_identity(self):
        self.assertEqual(POSITION["repository"], STATE["repository"])
        policy = POSITION["integration_policy"]
        self.assertTrue(policy["preserve_repository_identity"])
        self.assertTrue(policy["preserve_lineage"])
        self.assertTrue(policy["presentation_independent"])
        self.assertEqual(STATE["principal_state"], "EVOLVING")


if __name__ == "__main__":
    unittest.main()
