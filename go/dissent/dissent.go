// Package dissent: concurrent multi-sensor fusion with HIGH-severity freeze.
// Babel: Go — CSP fan-in for sensor opinions (W4H: concurrent stream fold).
package dissent

import (
	"fmt"
	"sync"
)

type Severity int

const (
	Low Severity = iota
	Medium
	High
	Critical
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

type Receipt struct {
	TrackID        string
	Recommendation Recommendation
	Dissenters     []string
	FreezeReason   string
}

// FuseConcurrent collects opinions from N producers and freezes on HIGH+ dissent.
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

func fuse(trackID string, minSensors int, freezeAt Severity, ops []Opinion) Receipt {
	if len(ops) < minSensors {
		return Receipt{TrackID: trackID, Recommendation: InsufficientSensors, FreezeReason: "MIN_SENSORS"}
	}
	scores := map[Label]float64{}
	for _, o := range ops {
		scores[o.Label] += 1.0 + o.Confidence
	}
	var majority Label
	best := -1.0
	for l, s := range scores {
		if s > best {
			best = s
			majority = l
		}
	}
	var dissenters []string
	for _, o := range ops {
		if o.Label != majority {
			dissenters = append(dissenters, o.SensorID)
			if o.SevIfDiss >= freezeAt {
				return Receipt{
					TrackID: trackID, Recommendation: FrozenDissent, Dissenters: dissenters,
					FreezeReason: fmt.Sprintf("DISSENT:%s", o.SensorID),
				}
			}
		}
	}
	return Receipt{TrackID: trackID, Recommendation: ContinueObserve, Dissenters: dissenters}
}
