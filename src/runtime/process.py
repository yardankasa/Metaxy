from __future__ import annotations

import os
import sys

from core.contracts.resources import Resources

_PAGE_SIZE = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 4096


class ProcessResources(Resources):
    def rss_bytes(self) -> int:
        try:
            with open("/proc/self/statm", encoding="ascii") as handle:
                resident_pages = int(handle.read().split()[1])
            return resident_pages * _PAGE_SIZE
        except (OSError, IndexError, ValueError):
            import resource

            rss = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            if sys.platform == "darwin":
                return rss
            return rss * 1024

    def apply_address_space_limit(self, limit_bytes: int) -> bool:
        if limit_bytes <= 0:
            return False
        try:
            import resource
        except ImportError:
            return False
        rlimit_as = getattr(resource, "RLIMIT_AS", None)
        if rlimit_as is None:
            return False
        try:
            _soft, hard = resource.getrlimit(rlimit_as)
            new_hard = limit_bytes if hard == resource.RLIM_INFINITY else min(hard, limit_bytes)
            resource.setrlimit(rlimit_as, (min(limit_bytes, new_hard), new_hard))
        except (ValueError, OSError):
            return False
        return True
