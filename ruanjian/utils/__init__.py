"""Utility package.

Keep package imports lightweight so importing one utility module does not eagerly
load optional numerical dependencies such as numpy.
"""

from .cache import MemoryCache, cache, cache_key, cached, prefetcher, rate_limit

__all__ = [
    "MemoryCache",
    "cache",
    "cache_key",
    "cached",
    "prefetcher",
    "rate_limit",
]
