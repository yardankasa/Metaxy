from __future__ import annotations

from sqlalchemy import Float, Index, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class CheckRow(Base):
    __tablename__ = "checks"
    __table_args__ = (
        Index("idx_checks_proxy_checked", "proxy_id", "checked_at"),
        Index("idx_checks_series_checked", "series", "checked_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    proxy_id: Mapped[str] = mapped_column(String, nullable=False)
    series: Mapped[str] = mapped_column(String, nullable=False)
    checked_at: Mapped[float] = mapped_column(Float, nullable=False)
    success: Mapped[int] = mapped_column(Integer, nullable=False)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)


class DailyRollupRow(Base):
    __tablename__ = "daily_rollups"

    proxy_id: Mapped[str] = mapped_column(String, primary_key=True)
    day: Mapped[str] = mapped_column(String, primary_key=True)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False)
    fail_count: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)


class HourlyRollupRow(Base):
    __tablename__ = "hourly_rollups"
    __table_args__ = (Index("idx_hourly_rollups_hour", "hour"),)

    proxy_id: Mapped[str] = mapped_column(String, primary_key=True)
    hour: Mapped[str] = mapped_column(String, primary_key=True)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False)
    fail_count: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
