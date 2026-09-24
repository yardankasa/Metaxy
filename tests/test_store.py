from pathlib import Path

from conftest import run

from core.domain.check import CheckRecord, Series
from core.domain.windows import rates_from_checks
from memory.check_store import InMemoryCheckStore
from persistence.check_store import SqliteCheckStore

NOW = 1_700_000_000.0
FIRST = "203.0.113.10:8080"
SECOND = "203.0.113.11:8080"


def _records() -> list[CheckRecord]:
    return [
        CheckRecord(FIRST, Series.POOL, NOW - 60, True, 80.0, 204, None),
        CheckRecord(FIRST, Series.POOL, NOW - 120, False, 800.0, 500, "bad"),
        CheckRecord(SECOND, Series.POOL, NOW - 30, True, 40.0, 204, None),
        CheckRecord("egress", Series.EGRESS, NOW - 10, True, 200.0, 204, None),
        CheckRecord(FIRST, Series.POOL, NOW - 7200, False, 900.0, None, "old"),
    ]


def test_memory_and_sqlite_agree_on_windows(tmp_path: Path) -> None:
    run(_agree(tmp_path))


async def _agree(tmp_path: Path) -> None:
    records = _records()
    expected = rates_from_checks(records, [FIRST, SECOND], now=NOW, series=Series.POOL)
    memory = InMemoryCheckStore()
    await memory.open()
    await memory.record(records)
    sqlite = SqliteCheckStore(tmp_path / "health.sqlite")
    await sqlite.open()
    try:
        await sqlite.record(records)
        assert await memory.success_rates([FIRST, SECOND], now=NOW, series=Series.POOL) == expected
        assert await sqlite.success_rates([FIRST, SECOND], now=NOW, series=Series.POOL) == expected
        egress = await sqlite.success_rates([FIRST], now=NOW, series=Series.EGRESS)
        assert egress[FIRST].window_24h_total == 0
        await sqlite.rebuild_rollups(now=NOW, days=7, hours=48, series=Series.POOL)
        daily = await sqlite.daily_since(days=7, now=NOW)
        assert daily[FIRST][0].success_count == 1
        assert daily[FIRST][0].fail_count == 2
        assert "egress" not in daily
        stale = CheckRecord(FIRST, Series.POOL, NOW - 3 * 86400, False, None, None, "stale")
        await sqlite.record([stale])
        pruned = await sqlite.prune(now=NOW, retain_days=1)
        assert pruned == 1
    finally:
        await sqlite.close()
        await memory.close()
