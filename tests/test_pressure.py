from core.services.pressure import PressureGuard, PressurePolicy


class _Rss:
    def __init__(self, value: int) -> None:
        self.value = value

    def rss_bytes(self) -> int:
        return self.value

    def apply_address_space_limit(self, limit_bytes: int) -> bool:
        return False


def test_connection_cap_refuses_the_third_acquire() -> None:
    guard = PressureGuard(PressurePolicy(max_rss_mb=1024, max_connections=2), _Rss(1))
    assert guard.try_acquire() is True
    assert guard.try_acquire() is True
    assert guard.try_acquire() is False
    guard.release()
    assert guard.try_acquire() is True


def test_soft_rss_cap_refuses_new_work() -> None:
    guard = PressureGuard(PressurePolicy(max_rss_mb=1, max_connections=8), _Rss(2 * 1024 * 1024))
    assert guard.over_limit() is True
    assert guard.try_acquire() is False
