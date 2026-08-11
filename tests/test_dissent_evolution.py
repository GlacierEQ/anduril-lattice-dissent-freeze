from __future__ import annotations

import unittest

from src.dissent_freeze import (
    AgreementEnvelope,
    DissentTier,
    LatticeDissentFreezer,
    Recommendation,
    RecoveryDecision,
    SensorOpinion,
    Severity,
    TrackLabel,
)


def op(sid, label, conf=0.9, sev=Severity.LOW):
    return SensorOpinion(sid, label, conf, sev, signature=f"sig-{sid}")


class DissentEvolutionTests(unittest.TestCase):
    def test_medium_cluster_escalates_without_freezing(self):
        env = AgreementEnvelope(
            "T1",
            (
                op("n1", TrackLabel.NEUTRAL),
                op("n2", TrackLabel.NEUTRAL),
                op("n3", TrackLabel.NEUTRAL),
                op("h2", TrackLabel.HOSTILE_SIM, 0.8, Severity.MEDIUM),
                op("h1", TrackLabel.HOSTILE_SIM, 0.7, Severity.LOW),
            ),
        )
        receipt = LatticeDissentFreezer().fuse(env)
        self.assertEqual(receipt.recommendation, Recommendation.ESCALATE_REVIEW)
        self.assertEqual(receipt.dissent_tier, DissentTier.MEDIUM)
        self.assertEqual(receipt.dissenters, ("h1", "h2"))
        self.assertEqual(len(receipt.dissent_clusters), 1)
        cluster = receipt.dissent_clusters[0]
        self.assertEqual(cluster.label, TrackLabel.HOSTILE_SIM)
        self.assertEqual(cluster.sensor_ids, ("h1", "h2"))
        self.assertEqual(cluster.max_severity, Severity.MEDIUM)
        self.assertAlmostEqual(cluster.mean_confidence, 0.75)

    def test_multiple_dissent_hypotheses_remain_separate_clusters(self):
        env = AgreementEnvelope(
            "T2",
            (
                op("n1", TrackLabel.NEUTRAL),
                op("n2", TrackLabel.NEUTRAL),
                op("n3", TrackLabel.NEUTRAL),
                op("f1", TrackLabel.FRIENDLY, sev=Severity.LOW),
                op("h1", TrackLabel.HOSTILE_SIM, sev=Severity.MEDIUM),
            ),
        )
        receipt = LatticeDissentFreezer().fuse(env)
        self.assertEqual(
            tuple(cluster.label for cluster in receipt.dissent_clusters),
            (TrackLabel.FRIENDLY, TrackLabel.HOSTILE_SIM),
        )
        self.assertEqual(receipt.dissent_tier, DissentTier.MEDIUM)

    def test_critical_dissent_selects_deterministic_highest_severity_freeze(self):
        env = AgreementEnvelope(
            "T3",
            (
                op("n1", TrackLabel.NEUTRAL),
                op("n2", TrackLabel.NEUTRAL),
                op("n3", TrackLabel.NEUTRAL),
                op("z-high", TrackLabel.HOSTILE_SIM, sev=Severity.HIGH),
                op("a-critical", TrackLabel.FRIENDLY, sev=Severity.CRITICAL),
            ),
        )
        receipt = LatticeDissentFreezer().fuse(env)
        self.assertEqual(receipt.recommendation, Recommendation.FROZEN_DISSENT)
        self.assertEqual(receipt.dissent_tier, DissentTier.CRITICAL)
        self.assertEqual(receipt.freeze_reason, "DISSENT:a-critical:CRITICAL")
        self.assertIsNone(receipt.majority_label)

    def test_tied_vote_is_stable_across_input_order(self):
        first = AgreementEnvelope(
            "T4",
            (
                op("n1", TrackLabel.NEUTRAL),
                op("f1", TrackLabel.FRIENDLY),
                op("n2", TrackLabel.NEUTRAL),
                op("f2", TrackLabel.FRIENDLY),
            ),
            min_sensors=4,
        )
        second = AgreementEnvelope("T4", tuple(reversed(first.opinions)), min_sensors=4)
        freezer = LatticeDissentFreezer()
        a = freezer.fuse(first)
        b = freezer.fuse(second)
        self.assertEqual(a.majority_label, TrackLabel.FRIENDLY)
        self.assertEqual(a.majority_label, b.majority_label)
        self.assertEqual(a.dissenters, b.dissenters)
        self.assertEqual(first.fingerprint(), second.fingerprint())

    def test_recovery_requires_stability_and_only_recovers_to_review(self):
        freezer = LatticeDissentFreezer()
        frozen = freezer.fuse(
            AgreementEnvelope(
                "T5",
                (
                    op("n1", TrackLabel.NEUTRAL),
                    op("n2", TrackLabel.NEUTRAL),
                    op("h1", TrackLabel.HOSTILE_SIM, sev=Severity.HIGH),
                ),
            )
        )
        stable = AgreementEnvelope(
            "T5",
            (
                op("n1", TrackLabel.NEUTRAL),
                op("n2", TrackLabel.NEUTRAL),
                op("n3", TrackLabel.NEUTRAL),
            ),
        )
        early = freezer.assess_recovery(frozen, stable, stable_rounds=1)
        ready = freezer.assess_recovery(frozen, stable, stable_rounds=2)
        self.assertEqual(early.decision, RecoveryDecision.HOLD_FROZEN)
        self.assertEqual(early.reason, "STABILITY_WINDOW_INCOMPLETE")
        self.assertEqual(ready.decision, RecoveryDecision.RECOVER_TO_REVIEW)
        self.assertEqual(ready.reason, "STABLE_NON_FREEZING_EVIDENCE")
        self.assertEqual(ready.current_fusion.recommendation, Recommendation.CONTINUE_OBSERVE)

    def test_recovery_refuses_new_freeze_or_insufficient_sensors(self):
        freezer = LatticeDissentFreezer()
        frozen = freezer.fuse(
            AgreementEnvelope(
                "T6",
                (
                    op("n1", TrackLabel.NEUTRAL),
                    op("n2", TrackLabel.NEUTRAL),
                    op("h1", TrackLabel.HOSTILE_SIM, sev=Severity.HIGH),
                ),
            )
        )
        refreeze = AgreementEnvelope(
            "T6",
            (
                op("n1", TrackLabel.NEUTRAL),
                op("n2", TrackLabel.NEUTRAL),
                op("h2", TrackLabel.HOSTILE_SIM, sev=Severity.CRITICAL),
            ),
        )
        sparse = AgreementEnvelope("T6", (op("n1", TrackLabel.NEUTRAL),), min_sensors=3)
        self.assertEqual(
            freezer.assess_recovery(frozen, refreeze, stable_rounds=9).decision,
            RecoveryDecision.HOLD_FROZEN,
        )
        self.assertEqual(
            freezer.assess_recovery(frozen, sparse, stable_rounds=9).decision,
            RecoveryDecision.HOLD_FROZEN,
        )

    def test_duplicate_sensor_identity_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "sensor_id values must be unique"):
            AgreementEnvelope(
                "T7",
                (
                    op("same", TrackLabel.NEUTRAL),
                    op("same", TrackLabel.HOSTILE_SIM),
                    op("other", TrackLabel.NEUTRAL),
                ),
            )


if __name__ == "__main__":
    unittest.main()
