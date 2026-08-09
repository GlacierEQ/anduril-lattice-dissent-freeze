package dissent

import "testing"

func TestFreezeOnHighDissent(t *testing.T) {
	r := FuseConcurrent("T1", 3, High,
		func() Opinion { return Opinion{"s1", Neutral, 0.9, Low} },
		func() Opinion { return Opinion{"s2", Neutral, 0.9, Low} },
		func() Opinion { return Opinion{"s3", HostileSim, 0.9, High} },
	)
	if r.Recommendation != FrozenDissent {
		t.Fatalf("want FROZEN got %s", r.Recommendation)
	}
}

func TestAgreement(t *testing.T) {
	r := FuseConcurrent("T1", 3, High,
		func() Opinion { return Opinion{"s1", Neutral, 0.9, Low} },
		func() Opinion { return Opinion{"s2", Neutral, 0.8, Low} },
		func() Opinion { return Opinion{"s3", Neutral, 0.85, Low} },
	)
	if r.Recommendation != ContinueObserve {
		t.Fatalf("want CONTINUE got %s", r.Recommendation)
	}
}
