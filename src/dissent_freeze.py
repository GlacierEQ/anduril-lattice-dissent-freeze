"""Lattice dissent freeze — deterministic multi-sensor agreement envelopes.

The fusion surface preserves dissent instead of collapsing it into a majority-only
answer. Dissent is clustered across sensors by alternate track label, assigned a
severity tier, and converted into fail-closed recommendations. A previously frozen
track can only recover into human/system review after bounded stable rounds; this
module never auto-restores a frozen recommendation directly to normal operation.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum


class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class DissentTier(str, Enum):
    NONE = "NONE"
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


class RecoveryDecision(str, Enum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    HOLD_FROZEN = "HOLD_FROZEN"
    RECOVER_TO_REVIEW = "RECOVER_TO_REVIEW"


def digest(obj: object) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@dataclass(frozen=True)
class SensorOpinion:
    sensor_id: str
    label: TrackLabel
    confidence: float
    severity_if_dissent: Severity
    signature: str

    def __post_init__(self) -> None:
        if not self.sensor_id:
            raise ValueError("sensor_id must not be empty")
        if not self.signature:
            raise ValueError("signature must not be empty")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be in [0,1]")


@dataclass(frozen=True)
class AgreementEnvelope:
    track_id: str
    opinions: tuple[SensorOpinion, ...]
    min_sensors: int = 3

    def __post_init__(self) -> None:
        if not self.track_id:
            raise ValueError("track_id must not be empty")
        if self.min_sensors <= 0:
            raise ValueError("min_sensors must be positive")
        sensor_ids = [op.sensor_id for op in self.opinions]
        if len(sensor_ids) != len(set(sensor_ids)):
            raise ValueError("sensor_id values must be unique within an envelope")

    def fingerprint(self) -> str:
        return digest(
            {
                "track_id": self.track_id,
                "opinions": [
                    (
                        o.sensor_id,
                        o.label.value,
                        o.confidence,
                        o.severity_if_dissent.value,
                        o.signature,
                    )
                    for o in sorted(self.opinions, key=lambda op: op.sensor_id)
                ],
                "min_sensors": self.min_sensors,
            }
        )


@dataclass(frozen=True)
class DissentCluster:
    label: TrackLabel
    sensor_ids: tuple[str, ...]
    max_severity: Severity
    mean_confidence: float

    def fingerprint(self) -> str:
        return digest(
            {
                "label": self.label.value,
                "sensor_ids": list(self.sensor_ids),
                "max_severity": self.max_severity.value,
                "mean_confidence": self.mean_confidence,
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
    dissent_tier: DissentTier = DissentTier.NONE
    dissent_clusters: tuple[DissentCluster, ...] = ()

    def fingerprint(self) -> str:
        return digest(
            {
                "track_id": self.track_id,
                "recommendation": self.recommendation.value,
                "majority_label": (
                    None if self.majority_label is None else self.majority_label.value
                ),
                "dissenters": list(self.dissenters),
                "freeze_reason": self.freeze_reason,
                "envelope": self.envelope_fingerprint,
                "dissent_tier": self.dissent_tier.value,
                "dissent_clusters": [
                    {
                        "label": cluster.label.value,
                        "sensor_ids": list(cluster.sensor_ids),
                        "max_severity": cluster.max_severity.value,
                        "mean_confidence": cluster.mean_confidence,
                    }
                    for cluster in self.dissent_clusters
                ],
            }
        )


@dataclass(frozen=True)
class RecoveryReceipt:
    track_id: str
    decision: RecoveryDecision
    current_fusion: FusionReceipt
    stable_rounds: int
    required_stable_rounds: int
    reason: str

    def fingerprint(self) -> str:
        return digest(
            {
                "track_id": self.track_id,
                "decision": self.decision.value,
                "current_fusion": self.current_fusion.fingerprint(),
                "stable_rounds": self.stable_rounds,
                "required_stable_rounds": self.required_stable_rounds,
                "reason": self.reason,
            }
        )


_SEVERITY_RANK = {
    Severity.LOW: 1,
    Severity.MEDIUM: 2,
    Severity.HIGH: 3,
    Severity.CRITICAL: 4,
}
_TIER_FOR_SEVERITY = {
    Severity.LOW: DissentTier.LOW,
    Severity.MEDIUM: DissentTier.MEDIUM,
    Severity.HIGH: DissentTier.HIGH,
    Severity.CRITICAL: DissentTier.CRITICAL,
}


def _cluster_dissent(
    opinions: tuple[SensorOpinion, ...], majority: TrackLabel
) -> tuple[DissentCluster, ...]:
    grouped: dict[TrackLabel, list[SensorOpinion]] = {}
    for opinion in opinions:
        if opinion.label != majority:
            grouped.setdefault(opinion.label, []).append(opinion)

    clusters: list[DissentCluster] = []
    for label in sorted(grouped, key=lambda item: item.value):
        members = grouped[label]
        max_severity = max(
            (member.severity_if_dissent for member in members),
            key=lambda severity: _SEVERITY_RANK[severity],
        )
        clusters.append(
            DissentCluster(
                label=label,
                sensor_ids=tuple(sorted(member.sensor_id for member in members)),
                max_severity=max_severity,
                mean_confidence=sum(member.confidence for member in members) / len(members),
            )
        )
    return tuple(clusters)


def _dissent_tier(clusters: tuple[DissentCluster, ...]) -> DissentTier:
    if not clusters:
        return DissentTier.NONE
    max_severity = max(
        (cluster.max_severity for cluster in clusters),
        key=lambda severity: _SEVERITY_RANK[severity],
    )
    return _TIER_FOR_SEVERITY[max_severity]


class LatticeDissentFreezer:
    """Fail-closed fusion with tiered dissent and bounded frozen-state recovery."""

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

        # Weighted vote by count + confidence. Ties resolve by stable label value,
        # never by input or hash-map iteration order.
        scores: dict[TrackLabel, float] = {}
        for opinion in ops:
            scores[opinion.label] = scores.get(opinion.label, 0.0) + 1.0 + opinion.confidence
        majority = min(scores, key=lambda label: (-scores[label], label.value))

        clusters = _cluster_dissent(ops, majority)
        tier = _dissent_tier(clusters)
        dissenters = tuple(
            sorted(sensor_id for cluster in clusters for sensor_id in cluster.sensor_ids)
        )

        freeze_candidates = sorted(
            (
                opinion
                for opinion in ops
                if opinion.label != majority
                and _SEVERITY_RANK[opinion.severity_if_dissent]
                >= _SEVERITY_RANK[self.freeze_at]
            ),
            key=lambda opinion: (
                -_SEVERITY_RANK[opinion.severity_if_dissent],
                opinion.sensor_id,
            ),
        )
        freeze_reason = None
        if freeze_candidates:
            offender = freeze_candidates[0]
            freeze_reason = (
                f"DISSENT:{offender.sensor_id}:{offender.severity_if_dissent.value}"
            )

        majority_confidences = [
            opinion.confidence for opinion in ops if opinion.label == majority
        ]
        if freeze_reason:
            recommendation = Recommendation.FROZEN_DISSENT
            majority_out: TrackLabel | None = None
        elif tier is DissentTier.MEDIUM:
            recommendation = Recommendation.ESCALATE_REVIEW
            majority_out = majority
        elif majority is TrackLabel.UNKNOWN or any(
            confidence < 0.55 for confidence in majority_confidences
        ):
            recommendation = Recommendation.ESCALATE_REVIEW
            majority_out = majority
        else:
            recommendation = Recommendation.CONTINUE_OBSERVE
            majority_out = majority

        return FusionReceipt(
            track_id=envelope.track_id,
            recommendation=recommendation,
            majority_label=majority_out,
            dissenters=dissenters,
            freeze_reason=freeze_reason,
            envelope_fingerprint=envelope.fingerprint(),
            dissent_tier=tier,
            dissent_clusters=clusters,
        )

    def assess_recovery(
        self,
        previous: FusionReceipt,
        current_envelope: AgreementEnvelope,
        *,
        stable_rounds: int,
        required_stable_rounds: int = 2,
    ) -> RecoveryReceipt:
        """Assess recovery from a prior freeze without auto-restoring authority.

        Recovery is deliberately bounded: a frozen track must produce enough
        sensors, no new HIGH/CRITICAL freeze, a non-UNKNOWN majority, and the
        configured number of stable rounds. Even then it recovers only to review.
        """
        if previous.track_id != current_envelope.track_id:
            raise ValueError("previous and current track_id must match")
        if stable_rounds < 0:
            raise ValueError("stable_rounds must be non-negative")
        if required_stable_rounds <= 0:
            raise ValueError("required_stable_rounds must be positive")

        current = self.fuse(current_envelope)
        if previous.recommendation is not Recommendation.FROZEN_DISSENT:
            return RecoveryReceipt(
                track_id=previous.track_id,
                decision=RecoveryDecision.NOT_APPLICABLE,
                current_fusion=current,
                stable_rounds=stable_rounds,
                required_stable_rounds=required_stable_rounds,
                reason="PREVIOUS_NOT_FROZEN",
            )
        if current.recommendation in {
            Recommendation.FROZEN_DISSENT,
            Recommendation.INSUFFICIENT_SENSORS,
        }:
            return RecoveryReceipt(
                track_id=previous.track_id,
                decision=RecoveryDecision.HOLD_FROZEN,
                current_fusion=current,
                stable_rounds=stable_rounds,
                required_stable_rounds=required_stable_rounds,
                reason=f"CURRENT_{current.recommendation.value}",
            )
        if current.majority_label in {None, TrackLabel.UNKNOWN}:
            return RecoveryReceipt(
                track_id=previous.track_id,
                decision=RecoveryDecision.HOLD_FROZEN,
                current_fusion=current,
                stable_rounds=stable_rounds,
                required_stable_rounds=required_stable_rounds,
                reason="UNKNOWN_MAJORITY",
            )
        if stable_rounds < required_stable_rounds:
            return RecoveryReceipt(
                track_id=previous.track_id,
                decision=RecoveryDecision.HOLD_FROZEN,
                current_fusion=current,
                stable_rounds=stable_rounds,
                required_stable_rounds=required_stable_rounds,
                reason="STABILITY_WINDOW_INCOMPLETE",
            )
        return RecoveryReceipt(
            track_id=previous.track_id,
            decision=RecoveryDecision.RECOVER_TO_REVIEW,
            current_fusion=current,
            stable_rounds=stable_rounds,
            required_stable_rounds=required_stable_rounds,
            reason="STABLE_NON_FREEZING_EVIDENCE",
        )
