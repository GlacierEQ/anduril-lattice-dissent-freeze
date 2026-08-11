package dissent

import "testing"

func opinion(sensorID string, label Label, confidence float64, severity Severity) func() Opinion {
	return func() Opinion { return Opinion{sensorID, label, confidence, severity} }
}

func TestFreezeOnHighDissent(t *testing.T) {
	r := FuseConcurrent("T1", 3, High,
		opinion("s1", Neutral, 0.9, Low),
		opinion("s2", Neutral, 0.9, Low),
		opinion("s3", HostileSim, 0.9, High),
	)
	if r.Recommendation != FrozenDissent {
		t.Fatalf("want FROZEN got %s", r.Recommendation)
	}
	if r.DissentTier != TierHigh {
		t.Fatalf("want HIGH tier got %s", r.DissentTier)
	}
}

func TestAgreement(t *testing.T) {
	r := FuseConcurrent("T1", 3, High,
		opinion("s1", Neutral, 0.9, Low),
		opinion("s2", Neutral, 0.8, Low),
		opinion("s3", Neutral, 0.85, Low),
	)
	if r.Recommendation != ContinueObserve {
		t.Fatalf("want CONTINUE got %s", r.Recommendation)
	}
	if r.MajorityLabel != Neutral || r.DissentTier != TierNone {
		t.Fatalf("unexpected agreement receipt: %+v", r)
	}
}

func TestMediumDissentClustersAndEscalates(t *testing.T) {
	r := FuseConcurrent("T2", 3, High,
		opinion("n1", Neutral, 0.9, Low),
		opinion("n2", Neutral, 0.9, Low),
		opinion("n3", Neutral, 0.9, Low),
		opinion("h2", HostileSim, 0.8, Medium),
		opinion("h1", HostileSim, 0.7, Low),
	)
	if r.Recommendation != EscalateReview || r.DissentTier != TierMedium {
		t.Fatalf("want MEDIUM review got %+v", r)
	}
	if len(r.Clusters) != 1 {
		t.Fatalf("want one cluster got %+v", r.Clusters)
	}
	cluster := r.Clusters[0]
	if cluster.Label != HostileSim || cluster.MaxSeverity != Medium {
		t.Fatalf("unexpected cluster %+v", cluster)
	}
	if len(cluster.SensorIDs) != 2 || cluster.SensorIDs[0] != "h1" || cluster.SensorIDs[1] != "h2" {
		t.Fatalf("cluster sensor ordering not deterministic: %+v", cluster.SensorIDs)
	}
}

func TestMultipleDissentLabelsRemainSeparate(t *testing.T) {
	r := FuseConcurrent("T3", 3, High,
		opinion("n1", Neutral, 0.9, Low),
		opinion("n2", Neutral, 0.9, Low),
		opinion("n3", Neutral, 0.9, Low),
		opinion("f1", Friendly, 0.9, Low),
		opinion("h1", HostileSim, 0.9, Medium),
	)
	if len(r.Clusters) != 2 {
		t.Fatalf("want two dissent clusters got %+v", r.Clusters)
	}
	if r.Clusters[0].Label != Friendly || r.Clusters[1].Label != HostileSim {
		t.Fatalf("cluster order not deterministic: %+v", r.Clusters)
	}
}

func TestCriticalDissentWinsFreezeReasonDeterministically(t *testing.T) {
	r := FuseConcurrent("T4", 3, High,
		opinion("n1", Neutral, 0.9, Low),
		opinion("n2", Neutral, 0.9, Low),
		opinion("n3", Neutral, 0.9, Low),
		opinion("z-high", HostileSim, 0.9, High),
		opinion("a-critical", Friendly, 0.9, Critical),
	)
	if r.DissentTier != TierCritical || r.FreezeReason != "DISSENT:a-critical:CRITICAL" {
		t.Fatalf("unexpected critical freeze %+v", r)
	}
}

func TestTiedVoteIsStableAcrossProducerOrder(t *testing.T) {
	a := FuseConcurrent("T5", 4, High,
		opinion("n1", Neutral, 0.9, Low),
		opinion("f1", Friendly, 0.9, Low),
		opinion("n2", Neutral, 0.9, Low),
		opinion("f2", Friendly, 0.9, Low),
	)
	b := FuseConcurrent("T5", 4, High,
		opinion("f2", Friendly, 0.9, Low),
		opinion("n2", Neutral, 0.9, Low),
		opinion("f1", Friendly, 0.9, Low),
		opinion("n1", Neutral, 0.9, Low),
	)
	if a.MajorityLabel != Friendly || b.MajorityLabel != Friendly {
		t.Fatalf("tie did not resolve deterministically: %+v %+v", a, b)
	}
	if len(a.Dissenters) != len(b.Dissenters) || a.Dissenters[0] != b.Dissenters[0] || a.Dissenters[1] != b.Dissenters[1] {
		t.Fatalf("dissent ordering changed: %+v %+v", a.Dissenters, b.Dissenters)
	}
}

func TestBoundedRecoveryOnlyReleasesToReview(t *testing.T) {
	frozen := FuseConcurrent("T6", 3, High,
		opinion("n1", Neutral, 0.9, Low),
		opinion("n2", Neutral, 0.9, Low),
		opinion("h1", HostileSim, 0.9, High),
	)
	stable := FuseConcurrent("T6", 3, High,
		opinion("n1", Neutral, 0.9, Low),
		opinion("n2", Neutral, 0.9, Low),
		opinion("n3", Neutral, 0.9, Low),
	)
	early := AssessRecovery(frozen, stable, 1, 2)
	ready := AssessRecovery(frozen, stable, 2, 2)
	if early.Decision != RecoveryHoldFrozen || early.Reason != "STABILITY_WINDOW_INCOMPLETE" {
		t.Fatalf("early recovery should hold: %+v", early)
	}
	if ready.Decision != RecoveryToReview || ready.Reason != "STABLE_NON_FREEZING_EVIDENCE" {
		t.Fatalf("stable recovery should release only to review: %+v", ready)
	}
}

func TestRecoveryHoldsOnRefreeze(t *testing.T) {
	frozen := FuseConcurrent("T7", 3, High,
		opinion("n1", Neutral, 0.9, Low),
		opinion("n2", Neutral, 0.9, Low),
		opinion("h1", HostileSim, 0.9, High),
	)
	refreeze := FuseConcurrent("T7", 3, High,
		opinion("n1", Neutral, 0.9, Low),
		opinion("n2", Neutral, 0.9, Low),
		opinion("h2", HostileSim, 0.9, Critical),
	)
	decision := AssessRecovery(frozen, refreeze, 9, 2)
	if decision.Decision != RecoveryHoldFrozen {
		t.Fatalf("refreeze must hold: %+v", decision)
	}
}
