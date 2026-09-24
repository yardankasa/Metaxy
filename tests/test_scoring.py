from core.domain.score import ScoringPolicy, compute_score, latency_score


def test_latency_score_is_bounded() -> None:
    assert latency_score(None, 2000) == 0.0
    assert latency_score(0, 2000) == 1.0
    assert latency_score(1000, 2000) == 0.5
    assert latency_score(4000, 2000) == 0.0


def test_weights_sum_the_score() -> None:
    weights = ScoringPolicy(
        success_1h=0.30,
        success_24h=0.30,
        success_7d=0.15,
        healthy=0.15,
        latency=0.10,
        latency_ref_ms=2000,
    )
    assert compute_score(1, 1, 1, True, 0, weights) == 1.0
    assert compute_score(1, 1, 1, False, 0, weights) == 0.85
    mixed = compute_score(0.8, 0.5, 0.4, True, 1000, weights)
    expected = 0.30 * 0.8 + 0.30 * 0.5 + 0.15 * 0.4 + 0.15 + 0.10 * 0.5
    assert mixed == round(expected, 6)
