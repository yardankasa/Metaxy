from __future__ import annotations

from abc import ABC, abstractmethod


class Clock(ABC):
    @abstractmethod
    def now(self) -> float:
        """Epoch seconds."""

    @abstractmethod
    def monotonic(self) -> float:
        """A duration origin. Only differences are meaningful."""
