// Package dissent provides deterministic concurrent multi-sensor fusion with
// tiered dissent, HIGH+ freeze semantics, and bounded frozen-state recovery.
// Babel: Go — CSP fan-in for sensor opinions (W4H: concurrent stream fold).
package dissent

import (
	"fmt"
	"sort"
	"sync"
)

type Severity int

const (
	Low Severity = iota
	Medium
	High
	Critical
)

type DissentTier string

const (
	TierNone     DissentTier = "NONE"
	TierLow      DissentTier = "LOW"
	TierMedium   DissentTier = "MEDIUM"
	TierHigh     DissentTier = "HIGH"
	TierCritical DissentTier = "CRITICAL"
)

type Label string

const (
	Unknown    Label = "UNKNOWN"
	Friendly   Label = "FRIENDLY"
	Neutral    Label = "NEUTRAL"
	HostileSim Label = "HOSTILE_SIM"
)

type Opinion struct {
	SensorID   string
	Label      Label
	Confidence float64
	SevIfDiss  Severity
}

type Recommendation string

const (
	ContinueObserve     Recommendation = "CONTINUE_OBSERVE"
	EscalateReview      Recommendation = "ESCALATE_REVIEW"
	FrozenDissent       Recommendation = "FROZEN_DISSENT"
	InsufficientSensors Recommendation = "INSUFFICIENT_SENSORS"
)

type RecoveryDecision string

const (
	RecoveryNotApplicable RecoveryDecision = "NOT_APPLICABLE"
	RecoveryHoldFrozen    RecoveryDecision = "HOLD_FROZEN"
	RecoveryToReview      RecoveryDecision = "RECOVER_TO_REVIEW"
)

type DissentCluster struct {
	Label          Label
	SensorIDs      []string
	MaxSeverity    Severity
	MeanConfidence float64
}

type Receipt struct {
	TrackID        string
	Recommendation Recommendation
	MajorityLabel  Label
	Dissenters     []string
	FreezeReason   string
	DissentTier    DissentTier
	Clusters       []DissentCluster
}

type RecoveryReceipt struct {
	TrackID              string
	Decision             RecoveryDecision
	Current              Receipt
	StableRounds         int
	RequiredStableRounds int
	Reason               string
}

// FuseConcurrent collects opinions from N producers and deterministically folds
// them. Producer completion order cannot affect majority, dissent ordering, or
// freeze selection.
func FuseConcurrent(trackID string, minSensors int, freezeAt Severity, producers ...func() Opinion) Receipt {
	ch := make(chan Opinion, len(producers))
	var wg sync.WaitGroup
	for _, p := range producers {
		wg.Add(1)
		go func(fn func() Opinion) {
			defer wg.Done()
			ch <- fn()
		}(p)
	}
	go func() {
		wg.Wait()
		close(ch)
	}()
	ops := make([]Opinion, 0, len(producers))
	for o := range ch {
		ops = append(ops, o)
	}
	return fuse(trackID, minSensors, freezeAt, ops)
}

func tierForSeverity(severity Severity) DissentTier {
	switch severity {
	case Low:
		return TierLow
	case Medium:
		return TierMedium
	case High:
		return TierHigh
	case Critical:
		return TierCritical
	default:
		return TierNone
	}
}

func clusterDissent(ops []Opinion, majority Label) []DissentCluster {
	grouped := map[Label][]Opinion{}
	for _, opinion := range ops {
		if opinion.Label != majority {
			grouped[opinion.Label] = append(grouped[opinion.Label], opinion)
		}
	}
	labels := make([]string, 0, len(grouped))
	for label := range grouped {
		labels = append(labels, string(label))
	}
	sort.Strings(labels)

	clusters := make([]DissentCluster, 0, len(labels))
	for _, rawLabel := range labels {
		label := Label(rawLabel)
		members := grouped[label]
		sensorIDs := make([]string, 0, len(members))
		maxSeverity := Low
		confidenceTotal := 0.0
		for _, member := range members {
			sensorIDs = append(sensorIDs, member.SensorID)
			if member.SevIfDiss > maxSeverity {
				maxSeverity = member.SevIfDiss
			}
			confidenceTotal += member.Confidence
		}
		sort.Strings(sensorIDs)
		clusters = append(clusters, DissentCluster{
			Label:          label,
			SensorIDs:      sensorIDs,
			MaxSeverity:    maxSeverity,
			MeanConfidence: confidenceTotal / float64(len(members)),
		})
	}
	return clusters
}

func dissentTier(clusters []DissentCluster) DissentTier {
	if len(clusters) == 0 {
		return TierNone
	}
	maxSeverity := Low
	for _, cluster := range clusters {
		if cluster.MaxSeverity > maxSeverity {
			maxSeverity = cluster.MaxSeverity
		}
	}
	return tierForSeverity(maxSeverity)
}

func fuse(trackID string, minSensors int, freezeAt Severity, ops []Opinion) Receipt {
	if len(ops) < minSensors {
		return Receipt{
			TrackID:        trackID,
			Recommendation: InsufficientSensors,
			FreezeReason:   "MIN_SENSORS",
			DissentTier:    TierNone,
		}
	}

	scores := map[Label]float64{}
	for _, opinion := range ops {
		scores[opinion.Label] += 1.0 + opinion.Confidence
	}
	labels := make([]string, 0, len(scores))
	for label := range scores {
		labels = append(labels, string(label))
	}
	sort.Strings(labels)
	majority := Label(labels[0])
	best := scores[majority]
	for _, rawLabel := range labels[1:] {
		label := Label(rawLabel)
		if scores[label] > best {
			best = scores[label]
			majority = label
		}
	}

	clusters := clusterDissent(ops, majority)
	tier := dissentTier(clusters)
	dissenters := make([]string, 0)
	for _, cluster := range clusters {
		dissenters = append(dissenters, cluster.SensorIDs...)
	}
	sort.Strings(dissenters)

	freezeCandidates := make([]Opinion, 0)
	for _, opinion := range ops {
		if opinion.Label != majority && opinion.SevIfDiss >= freezeAt {
			freezeCandidates = append(freezeCandidates, opinion)
		}
	}
	sort.Slice(freezeCandidates, func(i, j int) bool {
		if freezeCandidates[i].SevIfDiss != freezeCandidates[j].SevIfDiss {
			return freezeCandidates[i].SevIfDiss > freezeCandidates[j].SevIfDiss
		}
		return freezeCandidates[i].SensorID < freezeCandidates[j].SensorID
	})

	if len(freezeCandidates) > 0 {
		offender := freezeCandidates[0]
		return Receipt{
			TrackID:        trackID,
			Recommendation: FrozenDissent,
			Dissenters:     dissenters,
			FreezeReason:   fmt.Sprintf("DISSENT:%s:%s", offender.SensorID, tierForSeverity(offender.SevIfDiss)),
			DissentTier:    tier,
			Clusters:       clusters,
		}
	}

	lowMajorityConfidence := false
	for _, opinion := range ops {
		if opinion.Label == majority && opinion.Confidence < 0.55 {
			lowMajorityConfidence = true
			break
		}
	}
	if tier == TierMedium || majority == Unknown || lowMajorityConfidence {
		return Receipt{
			TrackID:        trackID,
			Recommendation: EscalateReview,
			MajorityLabel:  majority,
			Dissenters:     dissenters,
			DissentTier:    tier,
			Clusters:       clusters,
		}
	}
	return Receipt{
		TrackID:        trackID,
		Recommendation: ContinueObserve,
		MajorityLabel:  majority,
		Dissenters:     dissenters,
		DissentTier:    tier,
		Clusters:       clusters,
	}
}

// AssessRecovery evaluates a previously frozen track against a new fused window.
// A successful assessment never jumps directly back to normal operation; it only
// releases the freeze into review after a bounded stability window.
func AssessRecovery(previous Receipt, current Receipt, stableRounds int, requiredStableRounds int) RecoveryReceipt {
	if previous.TrackID != current.TrackID {
		panic("previous and current TrackID must match")
	}
	if stableRounds < 0 {
		panic("stableRounds must be non-negative")
	}
	if requiredStableRounds <= 0 {
		panic("requiredStableRounds must be positive")
	}
	result := RecoveryReceipt{
		TrackID:              previous.TrackID,
		Current:              current,
		StableRounds:         stableRounds,
		RequiredStableRounds: requiredStableRounds,
	}
	if previous.Recommendation != FrozenDissent {
		result.Decision = RecoveryNotApplicable
		result.Reason = "PREVIOUS_NOT_FROZEN"
		return result
	}
	if current.Recommendation == FrozenDissent || current.Recommendation == InsufficientSensors {
		result.Decision = RecoveryHoldFrozen
		result.Reason = "CURRENT_" + string(current.Recommendation)
		return result
	}
	if current.MajorityLabel == "" || current.MajorityLabel == Unknown {
		result.Decision = RecoveryHoldFrozen
		result.Reason = "UNKNOWN_MAJORITY"
		return result
	}
	if stableRounds < requiredStableRounds {
		result.Decision = RecoveryHoldFrozen
		result.Reason = "STABILITY_WINDOW_INCOMPLETE"
		return result
	}
	result.Decision = RecoveryToReview
	result.Reason = "STABLE_NON_FREEZING_EVIDENCE"
	return result
}
