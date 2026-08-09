"""Lattice dissent freeze — multi-sensor agreement envelopes."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class TrackLabel(str, Enum):
    UNKNOWN = "UNKNOWN"
    FRIENDLY = "FRIENDLY"
    NEUTRAL = "NEUTRAL"
    HOSTILE_SIM = "HOSTILE_SIM"  # simulation label only


class Recommendation(str, Enum):
    CONTINUE_OBSERVE = "CONTINUE_OBSERVE"
    ESCALATE_REVIEW = "ESCALATE_REVIEW"
    FROZEN_DISSENT = "FROZEN_DISSENT"
    INSUFFICIENT_SENSORS = "INSUFFICIENT_SENSORS"


def digest(obj: object) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class SensorOpinion:
    sensor_id: str
    label: TrackLabel
    confidence: float
    severity_if_dissent: Severity
    signature: str

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be in [0,1]")


@dataclass(frozen=True)
class AgreementEnvelope:
    track_id: str
    opinions: tuple[SensorOpinion, ...]
    min_sensors: int = 3

    def fingerprint(self) -> str:
        return digest(
            {
                "track_id": self.track_id,
                "opinions": [
                    (o.sensor_id, o.label.value, o.confidence, o.severity_if_dissent.value, o.signature)
                    for o in self.opinions
                ],
                "min_sensors": self.min_sensors,
            }
        )


@dataclass(frozen=True)
class FusionReceipt:
    track_id: str
    recommendation: Recommendation
    majority_label: TrackLabel | None
    dissenters: tuple[str, ...]
    freeze_reason: str | None
    envelope_fingerprint: str

    def fingerprint(self) -> str:
        return digest(
            {
                "track_id": self.track_id,
                "recommendation": self.recommendation.value,
                "majority_label": None if self.majority_label is None else self.majority_label.value,
                "dissenters": list(self.dissenters),
                "freeze_reason": self.freeze_reason,
                "envelope": self.envelope_fingerprint,
            }
        )


_SEVERITY_RANK = {
    Severity.LOW: 1,
    Severity.MEDIUM: 2,
    Severity.HIGH: 3,
    Severity.CRITICAL: 4,
}


class LatticeDissentFreezer:
    """Fail-closed fusion: critical/high dissent freezes recommendations."""

    def __init__(self, freeze_at: Severity = Severity.HIGH):
        self.freeze_at = freeze_at

    def fuse(self, envelope: AgreementEnvelope) -> FusionReceipt:
        ops = envelope.opinions
        if len(ops) < envelope.min_sensors:
            return FusionReceipt(
                track_id=envelope.track_id,
                recommendation=Recommendation.INSUFFICIENT_SENSORS,
                majority_label=None,
                dissenters=tuple(),
                freeze_reason="MIN_SENSORS",
                envelope_fingerprint=envelope.fingerprint(),
            )

        # majority by count then confidence sum
        scores: dict[TrackLabel, float] = {}
        for o in ops:
            scores[o.label] = scores.get(o.label, 0.0) + 1.0 + o.confidence
        majority = max(scores.keys(), key=lambda k: scores[k])
        dissenters = tuple(o.sensor_id for o in ops if o.label != majority)

        freeze_reason = None
        for o in ops:
            if o.label == majority:
                continue
            if _SEVERITY_RANK[o.severity_if_dissent] >= _SEVERITY_RANK[self.freeze_at]:
                freeze_reason = f"DISSENT:{o.sensor_id}:{o.severity_if_dissent.value}"
                break

        if freeze_reason:
            rec = Recommendation.FROZEN_DISSENT
            maj_out: TrackLabel | None = None  # do not promote majority under freeze
        elif majority is TrackLabel.UNKNOWN or any(o.confidence < 0.55 for o in ops if o.label == majority):
            rec = Recommendation.ESCALATE_REVIEW
            maj_out = majority
        else:
            rec = Recommendation.CONTINUE_OBSERVE
            maj_out = majority

        return FusionReceipt(
            track_id=envelope.track_id,
            recommendation=rec,
            majority_label=maj_out,
            dissenters=dissenters,
            freeze_reason=freeze_reason,
            envelope_fingerprint=envelope.fingerprint(),
        )
