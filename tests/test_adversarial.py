from __future__ import annotations
import unittest
from src.dissent_freeze import (
    AgreementEnvelope, LatticeDissentFreezer, Recommendation, SensorOpinion, Severity, TrackLabel
)

def op(sid, label, conf=0.9, sev=Severity.LOW):
    return SensorOpinion(sid, label, conf, sev, signature=f"sig-{sid}")

class Adv(unittest.TestCase):
    def test_confidence_out_of_range(self):
        with self.assertRaises(ValueError):
            op("s1", TrackLabel.NEUTRAL, conf=1.5)
    def test_critical_dissent_freezes(self):
        env = AgreementEnvelope("T1", (
            op("s1", TrackLabel.NEUTRAL),
            op("s2", TrackLabel.NEUTRAL),
            op("s3", TrackLabel.HOSTILE_SIM, sev=Severity.CRITICAL),
        ))
        r = LatticeDissentFreezer().fuse(env)
        self.assertEqual(r.recommendation, Recommendation.FROZEN_DISSENT)
        self.assertIsNone(r.majority_label)
    def test_low_confidence_majority_escalates(self):
        env = AgreementEnvelope("T1", (
            op("s1", TrackLabel.NEUTRAL, conf=0.4),
            op("s2", TrackLabel.NEUTRAL, conf=0.4),
            op("s3", TrackLabel.NEUTRAL, conf=0.4),
        ))
        r = LatticeDissentFreezer().fuse(env)
        self.assertEqual(r.recommendation, Recommendation.ESCALATE_REVIEW)

if __name__ == "__main__":
    unittest.main()
