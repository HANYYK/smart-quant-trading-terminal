"""
共享市场数据获取模块
整合东方财富行情获取和模拟数据生成
"""
import random
import logging
import threading
import json
from datetime import datetime, timedelta
from typing import Optional, List
from pathlib import Path
import requests

logger = logging.getLogger(__name__)

_session = requests.Session()
_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.eastmoney.com/",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
})

CACHE_DURATION = timedelta(minutes=1)
DEFAULT_CACHE_DIR = Path("data/cache")
DEFAULT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
STOCK_CACHE_PATH = DEFAULT_CACHE_DIR / "stock_cache.json"

_stock_records_cache: Optional[List[dict]] = None
_stock_records_cache_time: Optional[datetime] = None
_cache_lock = threading.Lock()


def _get_base_stocks() -> List[tuple]:
    return [
        ("600519", "贵州茅台", 1680), ("600036", "招商银行", 34.5), ("000858", "五粮液", 145),
        ("000333", "美的集团", 58), ("601318", "中国平安", 44), ("002594", "比亚迪", 245),
        ("600276", "恒瑞医药", 48), ("300750", "宁德时代", 195), ("600887", "伊利股份", 28),
        ("002415", "海康威视", 34), ("601012", "隆基绿能", 24), ("000001", "平安银行", 11.5),
        ("600030", "中信证券", 19), ("002475", "立讯精密", 29), ("601888", "中国中免", 68),
        ("300059", "东方财富", 17), ("600900", "长江电力", 21), ("002714", "牧原股份", 48),
    ]


def generate_mock_data() -> List[dict]:
    base_stocks = _get_base_stocks()
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


def fetch_from_eastmoney() -> Optional[List[dict]]:
    try:
        url = "http://push2.eastmoney.com/api/qt/clist/get"
        params = {
            "pn": 1, "pz": 5000, "po": 1, "np": 1,
            "ut": "bd1d9ddb04089700cf9c27f6f7426281", "fltt": 2, "invt": 2,
            "fid": "f3", "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048",
            "fields": "f2,f3,f4,f6,f12,f14,f15,f16,f17",
            "_": str(int(datetime.now().timestamp() * 1000))
        }
        resp = _session.get(url, params=params, timeout=10)
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
        logger.warning(f"[行情] 东方财富接口请求失败: {e}")
    return None


def load_cache() -> Optional[List[dict]]:
    try:
        if STOCK_CACHE_PATH.exists():
            stat = STOCK_CACHE_PATH.stat()
            age = datetime.now() - datetime.fromtimestamp(stat.st_mtime)
            if age < timedelta(hours=2):
                with open(STOCK_CACHE_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("records", [])
    except Exception as e:
        logger.warning(f"[缓存] 读取失败: {e}")
    return None


def save_cache(records: List[dict]) -> None:
    try:
        STOCK_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(STOCK_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump({"records": records, "saved_at": datetime.now().isoformat()}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"[缓存] 保存失败: {e}")


def fetch_stock_records() -> List[dict]:
    global _stock_records_cache, _stock_records_cache_time
    now = datetime.now()

    if _stock_records_cache is not None and _stock_records_cache_time is not None:
        if now - _stock_records_cache_time < CACHE_DURATION:
            return _stock_records_cache

    with _cache_lock:
        if _stock_records_cache is not None and _stock_records_cache_time is not None:
            if now - _stock_records_cache_time < CACHE_DURATION:
                return _stock_records_cache

        cached = load_cache()
        if cached:
            _stock_records_cache = cached
            _stock_records_cache_time = datetime.now()
            logger.info(f"[行情缓存] 已加载 {len(cached)} 条")
            return cached

        records = fetch_from_eastmoney()
        if records:
            _stock_records_cache = records
            _stock_records_cache_time = datetime.now()
            save_cache(records)
            logger.info(f"[行情] 获取 {len(records)} 条")
            return records

        mock = generate_mock_data()
        _stock_records_cache = mock
        _stock_records_cache_time = datetime.now()
        logger.warning("[行情] 使用备用模拟数据")
        return mock


def warmup_cache() -> None:
    def _warmup():
        global _stock_records_cache, _stock_records_cache_time
        try:
            cached = load_cache()
            if cached:
                _stock_records_cache = cached
                _stock_records_cache_time = datetime.now()
                logger.info(f"[行情缓存] 预热完成，加载 {len(cached)} 条")
            else:
                records = fetch_from_eastmoney()
                if records:
                    _stock_records_cache = records
                    _stock_records_cache_time = datetime.now()
                    save_cache(records)
                    logger.info(f"[行情缓存] 预热完成，获取 {len(records)} 条")
                else:
                    logger.warning("[行情缓存] 预热使用备用数据")
        except Exception as e:
            logger.error(f"[行情缓存] 预热失败: {e}")
    threading.Thread(target=_warmup, daemon=True).start()


def get_market_summary() -> dict:
    records = fetch_stock_records()
    gainers = sum(1 for s in records if s["change_percent"] > 0)
    losers = sum(1 for s in records if s["change_percent"] < 0)
    return {
        "gainers": gainers, "losers": losers, "unchanged": len(records) - gainers - losers,
        "total_volume": round(sum(s["volume"] for s in records) / 100000000, 2),
        "total_amount": round(sum(s["amount"] for s in records) / 100000000, 2),
        "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
