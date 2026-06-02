"""
缓存工具模块 - 提升性能
使用内存缓存 + SQLite 持久化缓存
"""
import time
import threading
import hashlib
import collections
from typing import Any, Optional, Callable, Union
from functools import wraps
import logging

logger = logging.getLogger(__name__)


class CacheEntry:
    """缓存条目"""
    def __init__(self, value: Any, ttl: int):
        self.value = value
        self.expiry = time.time() + ttl if ttl > 0 else float('inf')

    def is_expired(self) -> bool:
        return time.time() > self.expiry


class MemoryCache:
    """线程安全的内存缓存（单例模式）"""
    _instance = None
    _instance_lock = threading.Lock()
    _MAX_SIZE = 1000

    def __new__(cls):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._cache = collections.OrderedDict()
                    cls._instance._lock_internal = threading.Lock()
                    cls._instance._hit_count = 0
                    cls._instance._miss_count = 0
        return cls._instance

    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        with self._lock_internal:
            entry = self._cache.get(key)
            if entry is None:
                self._miss_count += 1
                return None
            if entry.is_expired():
                del self._cache[key]
                self._miss_count += 1
                return None
            self._cache.move_to_end(key)
            self._hit_count += 1
            return entry.value

    def set(self, key: str, value: Any, ttl: int = 300) -> None:
        """设置缓存值"""
        with self._lock_internal:
            if key in self._cache:
                del self._cache[key]
            elif len(self._cache) >= self._MAX_SIZE:
                self._cache.popitem(last=False)
            self._cache[key] = CacheEntry(value, ttl)

    def delete(self, key: str) -> None:
        """删除缓存"""
        with self._lock_internal:
            self._cache.pop(key, None)

    def clear(self) -> None:
        """清空缓存"""
        with self._lock_internal:
            self._cache.clear()
            self._hit_count = 0
            self._miss_count = 0

    def cleanup_expired(self) -> int:
        """清理过期条目"""
        with self._lock_internal:
            expired_keys = [
                k for k, v in self._cache.items()
                if v.is_expired()
            ]
            for key in expired_keys:
                del self._cache[key]
            return len(expired_keys)

    def get_stats(self) -> dict:
        """获取缓存统计"""
        with self._lock_internal:
            total = self._hit_count + self._miss_count
            hit_rate = self._hit_count / total if total > 0 else 0
            return {
                "size": len(self._cache),
                "max_size": self._MAX_SIZE,
                "hits": self._hit_count,
                "misses": self._miss_count,
                "hit_rate": round(hit_rate * 100, 2)
            }


cache = MemoryCache()


def cached(ttl: int = 300, key_prefix: str = ""):
    """
    缓存装饰器

    Args:
        ttl: 缓存过期时间（秒）
        key_prefix: 缓存键前缀
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 生成缓存键
            key_parts = [key_prefix] if key_prefix else [func.__name__]
            key_parts.extend(str(arg) for arg in args if not isinstance(arg, type(None)))
            key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()) if v is not None)
            cache_key = hashlib.md5(":".join(key_parts).encode()).hexdigest()

            # 尝试获取缓存
            cached_value = cache.get(cache_key)
            if cached_value is not None:
                logger.debug(f"缓存命中: {cache_key}")
                return cached_value

            # 执行函数并缓存结果
            result = func(*args, **kwargs)
            cache.set(cache_key, result, ttl)
            logger.debug(f"缓存设置: {cache_key} (TTL: {ttl}s)")
            return result
        return wrapper
    return decorator


def cache_key(*args, **kwargs) -> str:
    """生成缓存键的辅助函数"""
    key_parts = [str(arg) for arg in args if arg is not None]
    key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()) if v is not None)
    return hashlib.md5(":".join(key_parts).encode()).hexdigest()


def rate_limit(max_calls: int = 60, window: int = 60):
    """限流装饰器 — 每个被装饰函数独立计数，避免跨路由干扰"""

    def decorator(func: Callable) -> Callable:
        call_times = {}  # 每个函数独立的调用记录
        _lock = threading.Lock()
        _last_cleanup = [0.0]
        @wraps(func)
        def wrapper(*args, **kwargs):
            from flask import request, jsonify
            client_ip = request.remote_addr or "unknown"
            now = time.time()

            with _lock:
                if now - _last_cleanup[0] > 60:
                    expired_keys = [k for k, v in call_times.items() if now - v[-1] >= window]
                    for k in expired_keys:
                        call_times.pop(k, None)
                    _last_cleanup[0] = now

                if client_ip not in call_times:
                    call_times[client_ip] = []

                call_times[client_ip] = [
                    t for t in call_times[client_ip]
                    if now - t < window
                ]

                if len(call_times[client_ip]) >= max_calls:
                    logger.warning(f"限流触发: {client_ip}")
                    return jsonify({
                        "success": False,
                        "error": "请求过于频繁，请稍后再试",
                        "retry_after": window
                    }), 429

                call_times[client_ip].append(now)

            return func(*args, **kwargs)
        return wrapper
    return decorator


class DataPrefetcher:
    """数据预取器"""
    def __init__(self):
        self._cache = cache
        self._prefetching = False

    def prefetch_market_data(self, stock_codes: list) -> None:
        """预取市场数据"""
        if self._prefetching:
            return
        self._prefetching = True

        def _background_fetch():
            try:
                from routes.market import fetch_realtime_data
                for code in stock_codes[:50]:
                    try:
                        fetch_realtime_data(code)
                    except Exception as e:
                        logger.warning(f"预取失败 {code}: {e}")
            finally:
                self._prefetching = False

        thread = threading.Thread(target=_background_fetch, daemon=True)
        thread.start()


prefetcher = DataPrefetcher()
