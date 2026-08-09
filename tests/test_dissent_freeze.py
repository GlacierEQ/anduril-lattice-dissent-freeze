from __future__ import annotations
import unittest
from src.dissent_freeze import (
    AgreementEnvelope, LatticeDissentFreezer, Recommendation, SensorOpinion, Severity, TrackLabel
)

def op(sid, label, conf=0.9, sev=Severity.LOW):
    return SensorOpinion(sid, label, conf, sev, signature=f"sig-{sid}")

class FreezeTests(unittest.TestCase):
    def test_agreement_observes(self):
        env = AgreementEnvelope("T1", (op("s1", TrackLabel.NEUTRAL), op("s2", TrackLabel.NEUTRAL), op("s3", TrackLabel.NEUTRAL)))
        r = LatticeDissentFreezer().fuse(env)
        self.assertEqual(r.recommendation, Recommendation.CONTINUE_OBSERVE)

    def test_high_dissent_freezes(self):
        env = AgreementEnvelope("T1", (
            op("s1", TrackLabel.NEUTRAL),
            op("s2", TrackLabel.NEUTRAL),
            op("s3", TrackLabel.HOSTILE_SIM, sev=Severity.HIGH),
        ))
        r = LatticeDissentFreezer().fuse(env)
        self.assertEqual(r.recommendation, Recommendation.FROZEN_DISSENT)
        self.assertIsNone(r.majority_label)

    def test_insufficient_sensors(self):
        env = AgreementEnvelope("T1", (op("s1", TrackLabel.NEUTRAL),), min_sensors=3)
        r = LatticeDissentFreezer().fuse(env)
        self.assertEqual(r.recommendation, Recommendation.INSUFFICIENT_SENSORS)

if __name__ == "__main__":
    unittest.main()
