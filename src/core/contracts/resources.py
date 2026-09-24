from __future__ import annotations

from abc import ABC, abstractmethod


class Resources(ABC):
    @abstractmethod
    def rss_bytes(self) -> int: ...

    @abstractmethod
    def apply_address_space_limit(self, limit_bytes: int) -> bool: ...
