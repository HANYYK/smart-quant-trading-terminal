"""
全自动行情中心 - 核心模块
"""
from datetime import datetime
from flask import Blueprint, jsonify, request

from utils.shared_cache import (
    fetch_stock_records, warmup_stock_cache,
    invalidate_stock_cache, get_cache_info
)

market_bp = Blueprint("market", __name__)

CACHE_DURATION_SECONDS = 60  # 缓存时长（秒），用于API响应


@market_bp.route("/api/stock/list")
def get_stock_list():
    try:
        page = request.args.get("page", 1, type=int)
        page_size = request.args.get("pageSize", 100, type=int)
        search = request.args.get("search", "").strip()
        force = request.args.get("force", "0") == "1"

        records = fetch_stock_records(force_refresh=force)

        stock_data = list(records)
        if search:
            keyword = search.lower()
            stock_data = [s for s in stock_data
                         if keyword in s["code"].lower()
                         or keyword in s["name"].lower()
                         or keyword in s["raw_code"]]

        stock_data.sort(key=lambda x: x["change_percent"], reverse=True)
        total = len(stock_data)
        start = (page - 1) * page_size

        cache_info = get_cache_info()

        return jsonify({
            "success": True,
            "data": stock_data[start:start + page_size],
            "total": total,
            "recordsTotal": len(records),
            "recordsFiltered": total,
            "cache_age": cache_info.get("age_seconds", 0),
            "source": "cache" if cache_info.get("cached") else "api"
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "data": [], "total": 0}), 500


@market_bp.route("/api/stock/ranking")
def get_ranking():
    try:
        limit = request.args.get("limit", 20, type=int)
        rank_type = request.args.get("type", "gainers")
        force = request.args.get("force", "0") == "1"
        records = fetch_stock_records(force_refresh=force)

        data = sorted(records, key=lambda x: x["change_percent"], reverse=(rank_type == "gainers"))
        return jsonify({"success": True, "data": data[:limit], "type": rank_type})
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "data": []}), 500


@market_bp.route("/api/market/summary")
def get_market_summary():
    try:
        force = request.args.get("force", "0") == "1"
        records = fetch_stock_records(force_refresh=force)
        gainers = sum(1 for s in records if s["change_percent"] > 0)
        losers = sum(1 for s in records if s["change_percent"] < 0)
        return jsonify({
            "success": True,
            "data": {
                "gainers": gainers, "losers": losers, "unchanged": len(records) - gainers - losers,
                "total_volume": round(sum(s["volume"] for s in records) / 100000000, 2),
                "total_amount": round(sum(s["amount"] for s in records) / 100000000, 2),
                "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@market_bp.route("/api/refresh", methods=["POST"])
def refresh_cache():
    """手动刷新行情缓存"""
    try:
        invalidate_stock_cache()
        records = fetch_stock_records(force_refresh=True)
        cache_info = get_cache_info()
        return jsonify({
            "success": True,
            "message": "缓存已刷新",
            "record_count": len(records),
            "cache_age": cache_info.get("age_seconds", 0)
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@market_bp.route("/api/status")
def get_cache_status():
    """获取缓存状态"""
    try:
        cache_info = get_cache_info()
        return jsonify({
            "success": True,
            "data": {
                "has_cache": cache_info.get("cached", False),
                "record_count": cache_info.get("count", 0),
                "cache_age": cache_info.get("age_seconds", 0),
                "cache_duration_seconds": CACHE_DURATION_SECONDS,
                "update_time": (
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    if cache_info.get("age_seconds") is not None else None
                )
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
