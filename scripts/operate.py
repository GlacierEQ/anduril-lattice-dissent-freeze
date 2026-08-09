#!/usr/bin/env python3
"""Cold-start: LatticeDissentFreezer high-dissent freeze path."""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from dissent_freeze import (
    AgreementEnvelope, LatticeDissentFreezer, Recommendation, SensorOpinion, Severity, TrackLabel
)

def main() -> int:
    env = AgreementEnvelope("T1", (
        SensorOpinion("s1", TrackLabel.NEUTRAL, 0.9, Severity.LOW, "sig-s1"),
        SensorOpinion("s2", TrackLabel.NEUTRAL, 0.9, Severity.LOW, "sig-s2"),
        SensorOpinion("s3", TrackLabel.HOSTILE_SIM, 0.95, Severity.HIGH, "sig-s3"),
    ))
    r = LatticeDissentFreezer().fuse(env)
    out = {
        "track_id": r.track_id,
        "recommendation": r.recommendation.value,
        "expected": Recommendation.FROZEN_DISSENT.value,
        "majority_label": None if r.majority_label is None else r.majority_label.value,
        "fingerprint": r.fingerprint(),
        "ok": r.recommendation is Recommendation.FROZEN_DISSENT and r.majority_label is None,
    }
    print(json.dumps(out, sort_keys=True))
    return 0 if out["ok"] else 1
if __name__ == "__main__":
    raise SystemExit(main())
