from conftest import sample_proxy, scoring, selection

from core.domain.check import CheckApply, SuccessRates
from core.services.pool import Pool


def _apply(proxy_id: str, success: bool, latency: float, checked_at: float) -> CheckApply:
    return CheckApply(proxy_id, success, latency, 204 if success else None, None if success else "fail", checked_at)


def _sweep(pool: Pool, results: list[CheckApply], rates: dict, now: float) -> None:
    pool.apply_sweep(results, rates, sweep_at=now, duration_seconds=1)


def test_two_failures_are_required_before_a_member_drops() -> None:
    first, second = sample_proxy("203.0.113.10", 8080), sample_proxy("203.0.113.11", 8080)
    pool = Pool([first, second], scoring=scoring(), selection=selection())
    now = 1_700_000_000.0
    rates = {first.id: SuccessRates(10, 10, 10, 10), second.id: SuccessRates(10, 10, 10, 10)}
    _sweep(pool, [_apply(first.id, True, 50, now), _apply(second.id, True, 80, now)], rates, now)
    assert pool.preferred_id == first.id
    _sweep(pool, [_apply(first.id, False, 50, now), _apply(second.id, True, 80, now)], rates, now)
    assert pool.get(first.id).healthy is True
    _sweep(pool, [_apply(first.id, False, 50, now), _apply(second.id, True, 80, now)], rates, now)
    assert pool.get(first.id).healthy is False
    assert pool.preferred_id == second.id


def test_a_small_lead_does_not_move_the_preferred_member() -> None:
    first, second = sample_proxy("203.0.113.10", 1), sample_proxy("203.0.113.11", 2)
    pool = Pool([first, second], scoring=scoring(), selection=selection())
    now = 1_700_000_000.0
    pool.apply_sweep(
        [_apply(first.id, True, 40, now), _apply(second.id, True, 40, now)],
        {first.id: SuccessRates(10, 10, 10, 10), second.id: SuccessRates(8, 10, 8, 10)},
        sweep_at=now,
        duration_seconds=1,
    )
    assert pool.preferred_id == first.id
    pool.apply_sweep(
        [_apply(first.id, True, 40, now), _apply(second.id, True, 40, now)],
        {first.id: SuccessRates(9, 10, 9, 10), second.id: SuccessRates(10, 10, 10, 10)},
        sweep_at=now,
        duration_seconds=1,
    )
    assert pool.preferred_id == first.id
    much = {first.id: SuccessRates(1, 10, 1, 10), second.id: SuccessRates(10, 10, 10, 10)}
    pair = [_apply(first.id, True, 40, now), _apply(second.id, True, 40, now)]
    _sweep(pool, pair, much, now)
    assert pool.preferred_id == first.id
    _sweep(pool, pair, much, now)
    assert pool.preferred_id == second.id


def test_a_zero_margin_follows_the_leader_immediately() -> None:
    first, second = sample_proxy("203.0.113.10", 1), sample_proxy("203.0.113.11", 2)
    pool = Pool([first, second], scoring=scoring(), selection=selection(score_switch_margin=0, switch_hold_sweeps=1))
    now = 1_700_000_000.0
    pool.apply_sweep(
        [_apply(first.id, True, 40, now), _apply(second.id, True, 40, now)],
        {first.id: SuccessRates(10, 10, 10, 10), second.id: SuccessRates(8, 10, 8, 10)},
        sweep_at=now,
        duration_seconds=1,
    )
    pool.apply_sweep(
        [_apply(first.id, True, 40, now), _apply(second.id, True, 40, now)],
        {first.id: SuccessRates(9, 10, 9, 10), second.id: SuccessRates(10, 10, 10, 10)},
        sweep_at=now,
        duration_seconds=1,
    )
    assert pool.preferred_id == second.id


def test_ranked_healthy_members_put_the_preferred_one_first() -> None:
    first, second = sample_proxy("203.0.113.10", 1), sample_proxy("203.0.113.11", 2)
    pool = Pool([first, second], scoring=scoring(), selection=selection(score_switch_margin=0.5, switch_hold_sweeps=9))
    now = 1_700_000_000.0
    pool.apply_sweep(
        [_apply(first.id, True, 200, now), _apply(second.id, True, 10, now)],
        {first.id: SuccessRates(10, 10, 10, 10), second.id: SuccessRates(10, 10, 10, 10)},
        sweep_at=now,
        duration_seconds=1,
    )
    ranked = pool.healthy_ranked()
    assert ranked[0].id == pool.preferred_id
    assert {proxy.id for proxy in ranked} == {first.id, second.id}
