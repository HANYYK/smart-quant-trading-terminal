"""
统一的市场数据缓存模块

供 routes/stock.py 和 routes/market.py 共同使用，消除重复代码。
"""

import json
import os
import random
import threading
from datetime import datetime, timedelta
from typing import Optional

import requests

_stock_records_cache: Optional[list] = None
_stock_records_cache_time: Optional[datetime] = None
_refresh_lock = threading.Lock()
_force_refresh_flag = False
CACHE_DURATION = timedelta(minutes=1)

_cache_dir = os.environ.get("CACHE_DIR") or os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "cache"
)
_file_cache_path = os.path.join(_cache_dir, "stock_cache.json")

_market_session = requests.Session()
_market_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.eastmoney.com/",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
})


def _load_file_cache() -> Optional[list]:
    try:
        if os.path.exists(_file_cache_path):
            stat = os.stat(_file_cache_path)
            age = datetime.now() - datetime.fromtimestamp(stat.st_mtime)
            if age < timedelta(hours=2):
                with open(_file_cache_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("records", [])
    except Exception:
        pass
    return None


def _save_file_cache(records: list) -> None:
    try:
        os.makedirs(_cache_dir, exist_ok=True)
        with open(_file_cache_path, "w", encoding="utf-8") as f:
            json.dump({"records": records, "saved_at": datetime.now().isoformat()}, f, ensure_ascii=False)
    except Exception:
        pass


def _get_mock_data() -> list:
    """备用模拟数据（仅当真实接口不可用时使用）"""
    base_stocks = [
        ("600519", "贵州茅台", 1680), ("600036", "招商银行", 34.5), ("000858", "五粮液", 145),
        ("000333", "美的集团", 58), ("601318", "中国平安", 44), ("002594", "比亚迪", 245),
        ("600276", "恒瑞医药", 48), ("300750", "宁德时代", 195), ("600887", "伊利股份", 28),
        ("002415", "海康威视", 34), ("601012", "隆基绿能", 24), ("000001", "平安银行", 11.5),
        ("600030", "中信证券", 19), ("002475", "立讯精密", 29), ("601888", "中国中免", 68),
        ("300059", "东方财富", 17), ("600900", "长江电力", 21), ("002714", "牧原股份", 48),
    ]
    records = []
    for code, name, base in base_stocks:
        change = random.uniform(-8, 8)
        close = base * (1 + change / 100)
        open_p = base * (1 + random.uniform(-1.5, 1.5) / 100)
        high = max(close, open_p) * (1 + random.uniform(0, 1.5) / 100)
        low = min(close, open_p) * (1 - random.uniform(0, 1.5) / 100)
        prefix = "sh" if code.startswith("6") else "sz"
        records.append({
            "code": f"{prefix}{code}", "raw_code": code, "name": name,
            "open": round(open_p, 2), "high": round(high, 2), "low": round(low, 2),
            "close": round(close, 2), "volume": random.randint(500000, 30000000),
            "amount": random.randint(5000000, 300000000), "change_percent": round(change, 2),
            "change_amount": round(close - base, 2), "turn": round(random.uniform(0.5, 12), 2),
        })
    return records


def fetch_realtime_data() -> Optional[list]:
    """获取东方财富实时行情数据"""
    try:
        url = "http://push2.eastmoney.com/api/qt/clist/get"
        params = {
            "pn": 1, "pz": 5000, "po": 1, "np": 1,
            "ut": "bd1d9ddb04089700cf9c27f6f7426281", "fltt": 2, "invt": 2,
            "fid": "f3", "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048",
            "fields": "f2,f3,f4,f6,f12,f14,f15,f16,f17",
            "_": str(int(datetime.now().timestamp() * 1000))
        }
        resp = _market_session.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("data") and data["data"].get("diff"):
                records = []
                for item in data["data"]["diff"]:
                    code = str(item.get("f12", ""))
                    if not code or len(code) < 6:
                        continue
                    records.append({
                        "code": f"sh{code}" if code.startswith("6") else f"sz{code}",
                        "raw_code": code, "name": item.get("f14", ""),
                        "open": item.get("f17", 0) or 0, "high": item.get("f15", 0) or 0,
                        "low": item.get("f16", 0) or 0, "close": item.get("f2", 0) or 0,
                        "volume": item.get("f6", 0) or 0, "amount": 0,
                        "change_percent": item.get("f3", 0) or 0,
                        "change_amount": item.get("f4", 0) or 0, "turn": 0,
                    })
                return records
    except Exception as e:
        print(f"[行情] 接口请求失败: {e}")
    return None


def fetch_stock_records(force_refresh: bool = False) -> list:
    """获取股票行情列表（带缓存）"""
    global _stock_records_cache, _stock_records_cache_time, _force_refresh_flag

    now = datetime.now()

    if force_refresh:
        _force_refresh_flag = True

    if _stock_records_cache and _stock_records_cache_time:
        if now - _stock_records_cache_time < CACHE_DURATION and not _force_refresh_flag:
            return _stock_records_cache

    with _refresh_lock:
        if _stock_records_cache and _stock_records_cache_time:
            if now - _stock_records_cache_time < CACHE_DURATION and not _force_refresh_flag:
                return _stock_records_cache

        _force_refresh_flag = False
        cached = _load_file_cache()
        if cached:
            _stock_records_cache = cached
            _stock_records_cache_time = datetime.now()
            return cached

        records = fetch_realtime_data()
        if records:
            _stock_records_cache = records
            _stock_records_cache_time = datetime.now()
            _save_file_cache(records)
            return records

        mock = _get_mock_data()
        _stock_records_cache = mock
        _stock_records_cache_time = datetime.now()
        return mock


def invalidate_stock_cache() -> None:
    """手动失效缓存，下次请求会重新获取"""
    global _stock_records_cache, _stock_records_cache_time, _force_refresh_flag
    _stock_records_cache = None
    _stock_records_cache_time = None
    _force_refresh_flag = False


def get_cache_info() -> dict:
    """获取缓存状态信息"""
    global _stock_records_cache, _stock_records_cache_time
    return {
        "cached": _stock_records_cache is not None,
        "count": len(_stock_records_cache) if _stock_records_cache else 0,
        "age_seconds": (
            int((datetime.now() - _stock_records_cache_time).total_seconds())
            if _stock_records_cache_time else None
        ),
    }


def warmup_stock_cache() -> None:
    """后台线程预热缓存"""
    def _warmup():
        global _stock_records_cache, _stock_records_cache_time
        try:
            cached = _load_file_cache()
            if cached:
                _stock_records_cache = cached
                _stock_records_cache_time = datetime.now()
                print(f"[行情缓存] 已加载 {len(cached)} 条")
            else:
                records = fetch_realtime_data()
                if records:
                    _stock_records_cache = records
                    _stock_records_cache_time = datetime.now()
                    _save_file_cache(records)
                    print(f"[行情缓存] 预热完成 {len(records)} 条")
                else:
                    mock = _get_mock_data()
                    _stock_records_cache = mock
                    _stock_records_cache_time = datetime.now()
                    print("[行情缓存] 预热使用备用数据")
        except Exception as e:
            print(f"[行情缓存] 预加载失败: {e}")

    threading.Thread(target=_warmup, daemon=True).start()
