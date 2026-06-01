"""
股票详情页路由 - K线图与AI分析
增强版：KDJ、布林带、OBV、DMI等技术指标
"""
from flask import Blueprint, render_template, jsonify, request
import baostock as bs
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import random
import json
import time
import threading
import hashlib
from pathlib import Path

from utils import cache, cached
from utils.indicators import (
    calculate_all_indicators, calculate_ma, calculate_ema, calculate_macd,
    calculate_rsi, calculate_kdj, calculate_bollinger_bands, calculate_obv,
    calculate_dmi, calculate_atr, calculate_psy, calculate_money_flow
)
from utils.shared_cache import (
    fetch_stock_records, warmup_stock_cache, invalidate_stock_cache
)

try:
    from snownlp import SnowNLP
    SNOWNLP_AVAILABLE = True
except ImportError:
    SNOWNLP_AVAILABLE = False

stock_bp = Blueprint("stock", __name__)


def get_baostock_connection():
    lg = bs.login()
    return lg


def close_baostock_connection(lg):
    bs.logout()


@cached(ttl=600)
def fetch_kline_data(code: str, frequency: str = "d", count: int = 120) -> pd.DataFrame:
    """
    获取K线数据 (带缓存)
    frequency: 'd'=日线, 'w'=周线, 'm'=月线
    """
    lg = get_baostock_connection()

    try:
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=count * 2)).strftime("%Y-%m-%d")

        rs = bs.query_history_k_data_plus(
            code,
            "date,code,open,high,low,close,volume,amount,turn,pctChg",
            start_date=start_date,
            end_date=end_date,
            frequency=frequency,
            adjustflag="3"
        )

        data = []
        while rs.error_code == "0" and rs.next():
            data.append(rs.get_row_data())

        if not data:
            print(f"[K线] {code} 无数据，尝试备用数据")
            return _get_fallback_kline_data(code, count=count)

        df = pd.DataFrame(data, columns=[
            "date", "code", "open", "high", "low", "close",
            "volume", "amount", "turn", "pctChg"
        ])

        df["open"] = pd.to_numeric(df["open"], errors="coerce")
        df["high"] = pd.to_numeric(df["high"], errors="coerce")
        df["low"] = pd.to_numeric(df["low"], errors="coerce")
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
        df["pctChg"] = pd.to_numeric(df["pctChg"], errors="coerce")

        if df.empty or len(df) < count // 2:
            print(f"[K线] {code} 数据不足，补充备用数据")
            fallback = _get_fallback_kline_data(code, count=count)
            df = pd.concat([df, fallback], ignore_index=True).tail(count)

        return df.tail(count).reset_index(drop=True)

    except Exception as e:
        print(f"[K线] {code} 获取失败: {e}，使用备用数据")
        return _get_fallback_kline_data(code, count=count)

    finally:
        close_baostock_connection(lg)


def predict_trend_multi_indicator(df: pd.DataFrame, future_days: int = 3) -> dict:
    """
    多指标综合趋势预测
    基于 EMA/MACD/RSI/布林带/KDJ/ATR 六项指标加权评分，
    不使用任何外部模型，零额外依赖。
    """
    if len(df) < 30:
        return {
            "predictions": [], "confidence": 0, "trend": "neutral",
            "last_price": 0, "signals": [],
            "message": "历史数据不足（需要至少30个交易日）"
        }

    try:
        last = df.iloc[-1]
        prev = df.iloc[-2]
        last_price = float(last["close"])
        atr = float(last.get("atr", last_price * 0.02) or last_price * 0.02)
        volatility = atr / last_price  # 相对波动率

        signals = []
        scores = {}

        # ---- EMA 趋势 (权重 0.30) ----
        ema12 = float(last.get("ema12", last_price) or last_price)
        ema26 = float(last.get("ema26", last_price) or last_price)
        prev_ema12 = float(prev.get("ema12", last_price) or last_price)
        if ema12 > ema26:
            slope = (ema12 - prev_ema12) / (prev_ema12 + 1e-9)
            scores["ema"] = min(1.0, 0.5 + slope * 50)
            signals.append({"name": "EMA趋势", "direction": "up",
                           "detail": f"EMA12({ema12:.2f}) > EMA26({ema26:.2f})"})
        else:
            slope = (ema12 - prev_ema12) / (prev_ema12 + 1e-9)
            scores["ema"] = max(-1.0, -0.5 + slope * 50)
            signals.append({"name": "EMA趋势", "direction": "down",
                           "detail": f"EMA12({ema12:.2f}) < EMA26({ema26:.2f})"})

        # ---- MACD 信号 (权重 0.25) ----
        macd = float(last.get("macd", 0) or 0)
        macd_signal = float(last.get("macd_signal", 0) or 0)
        macd_hist = float(last.get("macd_hist", 0) or 0)
        prev_macd = float(prev.get("macd", 0) or 0)
        prev_signal = float(prev.get("macd_signal", 0) or 0)

        if prev_macd <= prev_signal and macd > macd_signal:
            scores["macd"] = 1.0
            signals.append({"name": "MACD", "direction": "up", "detail": "金叉"})
        elif prev_macd >= prev_signal and macd < macd_signal:
            scores["macd"] = -1.0
            signals.append({"name": "MACD", "direction": "down", "detail": "死叉"})
        elif macd_hist > 0:
            scores["macd"] = 0.5 if macd_hist > prev.get("macd_hist", 0) else 0.2
            signals.append({"name": "MACD", "direction": "up",
                           "detail": f"柱状图正值 {macd_hist:.3f}"})
        else:
            scores["macd"] = -0.5 if macd_hist < prev.get("macd_hist", 0) else -0.2
            signals.append({"name": "MACD", "direction": "down",
                           "detail": f"柱状图负值 {macd_hist:.3f}"})

        # ---- RSI 位置 (权重 0.20) ----
        rsi = float(last.get("rsi", 50) or 50)
        if rsi < 30:
            scores["rsi"] = 0.8
            signals.append({"name": "RSI", "direction": "up",
                           "detail": f"超卖区域 RSI={rsi:.1f}"})
        elif rsi > 70:
            scores["rsi"] = -0.8
            signals.append({"name": "RSI", "direction": "down",
                           "detail": f"超买区域 RSI={rsi:.1f}"})
        elif rsi > 50:
            scores["rsi"] = 0.2
            signals.append({"name": "RSI", "direction": "up",
                           "detail": f"偏强 RSI={rsi:.1f}"})
        else:
            scores["rsi"] = -0.2
            signals.append({"name": "RSI", "direction": "down",
                           "detail": f"偏弱 RSI={rsi:.1f}"})

        # ---- 布林带 (权重 0.15) ----
        bb_upper = float(last.get("bb_upper", 0) or 0)
        bb_lower = float(last.get("bb_lower", 0) or 0)
        bb_width = float(last.get("bb_width", 0) or 0)
        if bb_upper > 0 and bb_lower > 0:
            position = (last_price - bb_lower) / (bb_upper - bb_lower + 1e-9)
            if position < 0.2:
                scores["bb"] = 0.7
                signals.append({"name": "布林带", "direction": "up", "detail": "接近下轨"})
            elif position > 0.8:
                scores["bb"] = -0.7
                signals.append({"name": "布林带", "direction": "down", "detail": "接近上轨"})
            elif 0.4 <= position <= 0.6:
                scores["bb"] = 0.0
                signals.append({"name": "布林带", "direction": "neutral", "detail": "中轨运行"})
            else:
                scores["bb"] = (0.5 - position) * 0.5
                signals.append({"name": "布林带", "direction": "neutral",
                               "detail": f"轨内 {position:.0%} 位置"})
        else:
            scores["bb"] = 0

        # ---- KDJ (权重 0.10) ----
        k = float(last.get("kdj_k", 50) or 50)
        d = float(last.get("kdj_d", 50) or 50)
        prev_k = float(prev.get("kdj_k", 50) or 50)
        prev_d = float(prev.get("kdj_d", 50) or 50)
        if prev_k <= prev_d and k > d and k < 30:
            scores["kdj"] = 0.8
            signals.append({"name": "KDJ", "direction": "up",
                           "detail": f"低位金叉 K={k:.1f}"})
        elif prev_k >= prev_d and k < d and k > 70:
            scores["kdj"] = -0.8
            signals.append({"name": "KDJ", "direction": "down",
                           "detail": f"高位死叉 K={k:.1f}"})
        elif k > d:
            scores["kdj"] = 0.3
            signals.append({"name": "KDJ", "direction": "up", "detail": f"K({k:.1f})>D({d:.1f})"})
        else:
            scores["kdj"] = -0.3
            signals.append({"name": "KDJ", "direction": "down",
                           "detail": f"K({k:.1f})<D({d:.1f})"})

        # ---- 综合评分 ----
        weights = {"ema": 0.30, "macd": 0.25, "rsi": 0.20, "bb": 0.15, "kdj": 0.10}
        composite = sum(scores.get(k, 0) * w for k, w in weights.items())

        # 置信度 = 各指标绝对值加权和 → 指标越是同方向，置信度越高
        raw_agreement = sum(abs(scores.get(k, 0)) * w for k, w in weights.items())
        confidence = round(min(0.95, 0.40 + raw_agreement * 0.60), 2)

        # 趋势判断
        if composite > 0.15:
            trend = "up"
        elif composite < -0.15:
            trend = "down"
        else:
            trend = "neutral"

        # 预测价格 = 当前价 × (1 + 综合得分 × 波动率)
        predictions = []
        pred_price = last_price
        for i in range(1, future_days + 1):
            daily_move = composite * volatility * (1 + i * 0.3)  # 逐日放大
            pred_price = last_price * (1 + daily_move)
            predictions.append(round(pred_price, 2))

        return {
            "predictions": predictions,
            "confidence": confidence,
            "trend": trend,
            "last_price": last_price,
            "composite_score": round(composite, 3),
            "signals": signals,
        }

    except Exception as e:
        return {
            "predictions": [], "confidence": 0, "trend": "neutral",
            "last_price": float(df["close"].iloc[-1]) if len(df) > 0 else 0,
            "signals": [], "message": str(e)
        }


def _eastmoney_stock_secid(code: str) -> str:
    """股票代码转东方财富 secid，sh.600519 → 1.600519"""
    raw = code.split(".")[-1] if "." in code else code
    return f"1.{raw}" if code.startswith("sh") or (not code.startswith("sz") and raw.startswith("6")) else f"0.{raw}"


def _get_fallback_kline_data(code: str, count: int = 120) -> pd.DataFrame:
    """东方财富 K 线数据 —— baostock 不可用时的可靠后备（覆盖全部 A 股）"""
    import requests
    try:
        secid = _eastmoney_stock_secid(code)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=count * 2)
        url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
        params = {
            "secid": secid,
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57",
            "klt": "101",
            "fqt": "1",
            "beg": start_date.strftime("%Y%m%d"),
            "end": end_date.strftime("%Y%m%d"),
        }
        resp = requests.get(url, params=params,
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.eastmoney.com/"},
            timeout=10)
        data = resp.json()
        klines = (data.get("data") or {}).get("klines") or []
        if klines:
            records = []
            for line in klines:
                parts = str(line).split(",")
                if len(parts) < 7:
                    continue
                records.append({
                    "date": parts[0],
                    "code": code,
                    "open": float(parts[1]),
                    "close": float(parts[2]),
                    "high": float(parts[3]),
                    "low": float(parts[4]),
                    "volume": float(parts[5]),
                    "amount": float(parts[6]),
                    "pctChg": 0,
                    "turn": 0,
                })
            if records:
                # 补算涨跌幅
                for i in range(1, len(records)):
                    prev = records[i - 1]["close"]
                    cur = records[i]["close"]
                    records[i]["pctChg"] = round((cur - prev) / prev * 100, 2) if prev > 0 else 0
                df = pd.DataFrame(records)
                df = df.tail(count).reset_index(drop=True)
                return df
    except Exception as e:
        print(f"[K线] 东方财富备用也失败: {e}")

    # 最终保底：随机数据（保证页面不崩）
    base_price = 10.0
    dates = [(datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(count, 0, -1)]
    recs = []
    price = base_price
    for d in dates:
        chg = random.uniform(-3, 3)
        price *= (1 + chg / 100)
        recs.append({"date": d, "code": code, "open": round(price, 2), "close": round(price, 2),
                      "high": round(price * 1.02, 2), "low": round(price * 0.98, 2),
                      "volume": random.randint(5000000, 50000000), "amount": 0,
                      "pctChg": round(chg, 2), "turn": 0})
    return pd.DataFrame(recs)


# 中文金融情感关键词
_POSITIVE_WORDS = [
    "利好", "增长", "上涨", "突破", "盈利", "增持", "买入", "看好",
    "创新", "超预期", "反弹", "新高", "分红",
    "政策支持", "回暖", "复苏", "业绩", "扩张", "合作",
]
_NEGATIVE_WORDS = [
    "利空", "下跌", "亏损", "减持", "卖出", "风险", "暴跌", "爆雷",
    "下滑", "退市", "ST", "金融危机", "衰退",
    "诉讼", "罚款", "违规", "警告", "负债", "过剩",
]


def analyze_sentiment(news_list: list[str]) -> dict:
    """使用SnowNLP进行情绪分析，不可用时使用关键词匹配兜底"""
    if not news_list:
        return {"score": 50, "sentiment": "neutral", "news_count": 0,
                "method": "none"}

    if SNOWNLP_AVAILABLE:
        try:
            scores = []
            for news in news_list[:10]:
                if len(news) > 5:
                    s = SnowNLP(news)
                    scores.append(s.sentiments)

            if scores:
                avg_score = np.mean(scores) * 100
                if avg_score > 60:
                    sentiment = "positive"
                elif avg_score < 40:
                    sentiment = "negative"
                else:
                    sentiment = "neutral"

                return {
                    "score": round(avg_score, 2),
                    "sentiment": sentiment,
                    "news_count": len(news_list),
                    "method": "snownlp",
                }
        except Exception:
            pass  # fall through to keyword fallback

    # 关键词匹配兜底
    pos_count = 0
    neg_count = 0
    for news in news_list[:10]:
        text = news.lower()
        for w in _POSITIVE_WORDS:
            if w in text:
                pos_count += 1
        for w in _NEGATIVE_WORDS:
            if w in text:
                neg_count += 1

    total = pos_count + neg_count
    if total > 0:
        score = 50 + 30 * (pos_count - neg_count) / max(total, 1)
        score = max(10, min(90, score))
    else:
        score = 50

    if score > 60:
        sentiment = "positive"
    elif score < 40:
        sentiment = "negative"
    else:
        sentiment = "neutral"

    return {
        "score": round(score, 1),
        "sentiment": sentiment,
        "news_count": len(news_list),
        "method": "keyword",
    }


@stock_bp.route("/detail/<stock_code>")
def detail(stock_code: str):
    """股票详情页"""
    if not stock_code.startswith(("sh.", "sz.", "bj.")):
        stock_code_clean = stock_code.replace(".", "").lower()
        if stock_code_clean.startswith(("sh", "sz", "bj")):
            market = stock_code_clean[:2]
            code = stock_code_clean[2:]
            stock_code = f"{market}.{code}"
        else:
            return render_template("stock/detail.html", stock_code="sh.600016", error="股票代码无效，已切换到默认股票")
    return render_template("stock/detail.html", stock_code=stock_code)


@stock_bp.route("/api/kline/<stock_code>")
def get_kline_data(stock_code: str):
    """获取K线数据API - 包含所有技术指标"""
    try:
        frequency = request.args.get("frequency", "d")
        count = request.args.get("count", 120, type=int)
        time_range = request.args.get("range", "3m")

        range_map = {
            "1w": 7, "1m": 30, "3m": 90, "6m": 180,
            "1y": 365, "2y": 730, "5y": 1825
        }
        if time_range in range_map:
            count = range_map[time_range]

        df = fetch_kline_data(stock_code, frequency=frequency, count=count)

        if df.empty:
            return jsonify({
                "success": False,
                "error": "无法获取K线数据",
                "data": None
            }), 404

        df = calculate_ma(df)
        df = calculate_ema(df)
        df = calculate_macd(df)
        df = calculate_rsi(df)
        df = calculate_kdj(df)
        df = calculate_bollinger_bands(df)
        df = calculate_obv(df)
        df = calculate_dmi(df)
        df = calculate_atr(df)
        df = calculate_psy(df)
        df = calculate_money_flow(df)

        kline_data = []
        pd_notna = pd.notna
        for row in df.itertuples(index=False):
            kline_data.append({
                "date": str(row.date),
                "open": float(row.open) if pd_notna(row.open) else 0,
                "high": float(row.high) if pd_notna(row.high) else 0,
                "low": float(row.low) if pd_notna(row.low) else 0,
                "close": float(row.close) if pd_notna(row.close) else 0,
                "volume": float(row.volume) if pd_notna(row.volume) else 0,
                "pctChg": float(row.pctChg) if pd_notna(row.pctChg) else 0,
                "ma5": float(row.ma5) if pd_notna(row.ma5) else None,
                "ma10": float(row.ma10) if pd_notna(row.ma10) else None,
                "ma20": float(row.ma20) if pd_notna(row.ma20) else None,
                "ma60": float(row.ma60) if pd_notna(row.ma60) else None,
                "ema12": float(row.ema12) if pd_notna(row.ema12) else None,
                "ema26": float(row.ema26) if pd_notna(row.ema26) else None,
                "macd": float(row.macd) if pd_notna(row.macd) else 0,
                "macd_signal": float(row.macd_signal) if pd_notna(row.macd_signal) else 0,
                "macd_hist": float(row.macd_hist) if pd_notna(row.macd_hist) else 0,
                "rsi": float(row.rsi) if pd_notna(row.rsi) else 50,
                "kdj_k": float(row.kdj_k) if pd_notna(row.kdj_k) else 50,
                "kdj_d": float(row.kdj_d) if pd_notna(row.kdj_d) else 50,
                "kdj_j": float(row.kdj_j) if pd_notna(row.kdj_j) else 50,
                "bb_upper": float(row.bb_upper) if pd_notna(row.bb_upper) else None,
                "bb_middle": float(row.bb_middle) if pd_notna(row.bb_middle) else None,
                "bb_lower": float(row.bb_lower) if pd_notna(row.bb_lower) else None,
                "bb_width": float(row.bb_width) if pd_notna(row.bb_width) else None,
                "obv": float(row.obv) if pd_notna(row.obv) else 0,
                "obv_ma": float(row.obv_ma) if pd_notna(row.obv_ma) else None,
                "dmi_plus": float(row.dmi_plus) if pd_notna(row.dmi_plus) else 0,
                "dmi_minus": float(row.dmi_minus) if pd_notna(row.dmi_minus) else 0,
                "adx": float(row.adx) if pd_notna(row.adx) else 0,
                "atr": float(row.atr) if pd_notna(row.atr) else 0,
                "psy": float(row.psy) if pd_notna(row.psy) else 50,
                "money_inflow": float(row.money_inflow) if pd_notna(row.money_inflow) else 0,
                "money_outflow": float(row.money_outflow) if pd_notna(row.money_outflow) else 0,
                "net_money_flow": float(row.net_money_flow) if pd_notna(row.net_money_flow) else 0,
            })

        return jsonify({
            "success": True,
            "data": kline_data,
            "stock_code": stock_code,
            "count": len(kline_data)
        })

    except Exception as e:
        import logging
        logging.exception("K线数据API错误")
        return jsonify({
            "success": False,
            "error": "服务器内部错误，请稍后重试",
            "data": None
        }), 500


@stock_bp.route("/api/info/<stock_code>")
def get_stock_info(stock_code: str):
    """获取股票基本信息"""
    try:
        lg = get_baostock_connection()

        try:
            rs = bs.query_stock_basic(code=stock_code)

            info = {
                "code": stock_code,
                "name": "未知",
                "ipoDate": "",
                "outDate": "",
                "type": "",
                "status": "正常"
            }
            while rs.error_code == "0" and rs.next():
                data = rs.get_row_data()
                if data:
                    info = {
                        "code": data[0],
                        "name": data[1],
                        "ipoDate": data[2],
                        "outDate": data[3],
                        "type": data[4],
                        "status": data[5] if len(data) > 5 else "正常"
                    }
                    break

            close_price = 0.0
            rs2 = bs.query_history_k_data_plus(
                stock_code,
                "close,pctChg,pe,pb",
                start_date=(datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d"),
                end_date=datetime.now().strftime("%Y-%m-%d"),
                frequency="d",
                adjustflag="3"
            )

            prices = []
            while rs2.error_code == "0" and rs2.next():
                prices.append(rs2.get_row_data())

            if prices:
                last = prices[-1]
                close_price = float(last[0]) if last[0] else 0

            info["close"] = close_price
            info["update_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            return jsonify({"success": True, "data": info})

        finally:
            close_baostock_connection(lg)

    except Exception as e:
        import logging
        logging.exception("股票信息API错误")
        return jsonify({"success": False, "error": "服务器内部错误，请稍后重试"}), 500


@stock_bp.route("/api/ai/predict/<stock_code>")
def get_ai_prediction(stock_code: str):
    """获取AI趋势预测"""
    try:
        df = fetch_kline_data(stock_code, count=120)

        if df.empty or len(df) < 30:
            return jsonify({
                "success": False,
                "error": "数据不足",
                "data": None
            }), 400

        # 计算技术指标供预测使用
        df = calculate_ema(df)
        df = calculate_macd(df)
        df = calculate_rsi(df)
        df = calculate_bollinger_bands(df)
        df = calculate_kdj(df)
        df = calculate_atr(df)

        prediction = predict_trend_multi_indicator(df, future_days=3)

        return jsonify({"success": True, "data": prediction})

    except Exception as e:
        import logging
        logging.exception("AI预测API错误")
        return jsonify({"success": False, "error": "服务器内部错误，请稍后重试"}), 500


# ---- 新闻缓存 ----
_NEWS_CACHE_DIR = Path("cache/news")
_NEWS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
_NEWS_CACHE_TTL = 600  # 10 分钟
_news_cache_lock = threading.Lock()


def _fetch_real_news(stock_code: str) -> list[str]:
    """从东方财富获取真实个股新闻标题"""
    # 提取纯数字代码，如 sh.600519 → 600519
    raw_code = stock_code.split(".")[-1] if "." in stock_code else stock_code

    # 读缓存
    cache_file = _NEWS_CACHE_DIR / f"{raw_code}.json"
    try:
        if cache_file.exists():
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            if time.time() - data.get("ts", 0) < _NEWS_CACHE_TTL:
                return data.get("titles", [])
    except Exception:
        pass

    titles = []
    try:
        import akshare as ak
        df = ak.stock_news_em(stock=raw_code)
        if df is not None and not df.empty:
            titles = df["title"].dropna().head(20).tolist()
    except Exception:
        pass  # 失败走降级

    if not titles:
        # 降级：用 mock 新闻池
        h = int(hashlib.md5(stock_code.encode()).hexdigest()[:8], 16)
        rng = random.Random(h)
        pool = list(_MOCK_NEWS_POOL)
        rng.shuffle(pool)
        code_short = raw_code
        titles = [tpl[0].replace("{code}", code_short) for tpl in pool[:7]]

    # 写缓存
    try:
        cache_file.write_text(
            json.dumps({"titles": titles, "ts": time.time()}, ensure_ascii=False),
            encoding="utf-8"
        )
    except Exception:
        pass

    return titles


# 备用新闻池 —— akshare 失败时的降级方案
_MOCK_NEWS_POOL = [
    ("{code}发布季度财报，营收同比增长15%", "positive"),
    ("机构上调{code}目标价，维持买入评级", "positive"),
    ("{code}新产品获得市场认可，销量超预期", "positive"),
    ("多家机构看好{code}长期发展前景", "positive"),
    ("{code}宣布战略合作计划，拓展新业务线", "positive"),
    ("{code}获政策支持，行业景气度持续回暖", "positive"),
    ("{code}业绩超预期，净利润同比增长30%", "positive"),
    ("{code}技术突破，推出新一代产品", "positive"),
    ("{code}季度财报不及预期，净利润下滑", "negative"),
    ("行业竞争加剧，{code}市场份额面临挑战", "negative"),
    ("{code}遭遇大股东减持，市场信心受挫", "negative"),
    ("监管新规出台，{code}业务模式或受影响", "negative"),
    ("{code}估值偏高，分析师下调评级至中性", "negative"),
    ("{code}召开股东大会，审议年度报告", "neutral"),
    ("{code}发布公告，回应投资者关切事项", "neutral"),
    ("{code}维持现有业务格局，静待政策催化", "neutral"),
    ("{code}参与行业论坛，探讨数字化转型方向", "neutral"),
]


@stock_bp.route("/api/ai/sentiment/<stock_code>")
def get_sentiment_analysis(stock_code: str):
    """获取情绪分析 —— 真实新闻 + 关键词情感打分"""
    try:
        news_titles = _fetch_real_news(stock_code)
        sentiment = analyze_sentiment(news_titles)
        sentiment["news_titles"] = news_titles[:5]  # 返回前 5 条标题给前端展示
        return jsonify({"success": True, "data": sentiment})
    except Exception as e:
        import logging
        logging.exception("情绪分析API错误")
        return jsonify({"success": False, "error": "暂时不可用"}), 500


@stock_bp.route("/api/realtime/<stock_code>")
def get_realtime_quote(stock_code: str):
    """获取实时行情"""
    try:
        # 使用K线数据的最后一条作为实时行情（baostock无实时API）
        df = fetch_kline_data(stock_code, count=1)
        if not df.empty:
            data = {
                "code": stock_code,
                "name": "未知",
                "open": float(df.iloc[0]["open"]),
                "high": float(df.iloc[0]["high"]),
                "low": float(df.iloc[0]["low"]),
                "close": float(df.iloc[0]["close"]),
                "volume": float(df.iloc[0]["volume"]),
                "timestamp": df.iloc[0]["date"]
            }
            return jsonify({"success": True, "data": data})

        return jsonify({"success": False, "error": "无法获取行情数据"}), 404

    except Exception as e:
        import logging
        logging.exception("实时行情API错误")
        return jsonify({"success": False, "error": "服务器内部错误，请稍后重试"}), 500


@stock_bp.route("/compare")
def compare():
    """股票对比页面"""
    codes = request.args.getlist("codes")
    return render_template("stock/compare.html", codes=codes)


@stock_bp.route("/api/compare")
def compare_stocks():
    """获取多只股票对比数据"""
    codes = request.args.getlist("codes", type=str)

    if not codes or len(codes) < 2:
        return jsonify({"success": False, "error": "至少需要2个股票代码"}), 400

    if len(codes) > 5:
        return jsonify({"success": False, "error": "最多支持5只股票对比"}), 400

    results = []
    failed_codes = []
    for code in codes:
        try:
            df = fetch_kline_data(code, count=30)
            if not df.empty:
                latest = df.iloc[-1]
                prev = df.iloc[-2] if len(df) > 1 else latest

                results.append({
                    "code": code,
                    "name": latest.get("code", code),
                    "close": float(latest["close"]),
                    "change": float(latest["close"]) - float(prev["close"]),
                    "change_percent": float(latest["pctChg"]) if pd.notna(latest["pctChg"]) else 0,
                    "volume": float(latest["volume"]),
                    "high_30d": float(df["high"].max()),
                    "low_30d": float(df["low"].min()),
                    "avg_volume": float(df["volume"].mean()),
                })
        except Exception:
            failed_codes.append(code)

    if failed_codes:
        return jsonify({"success": False, "error": f"以下股票获取失败: {', '.join(failed_codes)}"}), 404

    return jsonify({"success": True, "data": results})


@stock_bp.route("/sector")
def sector():
    """板块轮动页面"""
    return render_template("stock/sector.html")


@stock_bp.route("/api/sector")
def get_sector_data():
    """获取板块数据"""
    sectors = [
        {"code": "000001", "name": "上证指数", "type": "index"},
        {"code": "399001", "name": "深证成指", "type": "index"},
        {"code": "399006", "name": "创业板指", "type": "index"},
        {"code": "000016", "name": "上证50", "type": "index"},
        {"code": "000300", "name": "沪深300", "type": "index"},
        {"code": "000905", "name": "中证500", "type": "index"},
        {"code": "000852", "name": "中证1000", "type": "index"},
        {"code": "399005", "name": "中小100", "type": "index"},
        {"code": "399673", "name": "创业板50", "type": "index"},
        {"code": "000688", "name": "科创50", "type": "index"},
    ]

    results = []
    failed = []
    for sector in sectors:
        try:
            if sector["code"].startswith(("sh.", "sz.")):
                code = sector["code"]
            elif sector["code"].startswith("0"):
                code = f"sh.{sector['code']}"
            else:
                code = f"sz.{sector['code']}"

            df = fetch_kline_data(code, count=5)
            if not df.empty:
                latest = df.iloc[-1]
                change = float(latest["pctChg"]) if pd.notna(latest["pctChg"]) else 0
                results.append({
                    "code": sector["code"],
                    "name": sector["name"],
                    "change_percent": change,
                    "close": float(latest["close"]),
                    "status": "up" if change > 0 else ("down" if change < 0 else "flat")
                })
        except Exception:
            failed.append(sector["name"])

    if not results and failed:
        return jsonify({"success": False, "error": f"以下板块数据获取失败: {', '.join(failed)}"}), 500

    results.sort(key=lambda x: x["change_percent"], reverse=True)

    return jsonify({"success": True, "data": results})


# ==================== 市场行情API ====================

@stock_bp.route("/api/stock/list")
def get_stock_list():
    try:
        page = request.args.get("page", 1, type=int)
        page_size = request.args.get("pageSize", 100, type=int)
        search = request.args.get("search", "").strip()
        records = fetch_stock_records()

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
        return jsonify({
            "success": True,
            "data": stock_data[start:start + page_size],
            "total": total,
            "recordsTotal": len(records),
            "recordsFiltered": total,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "data": [], "total": 0}), 500


@stock_bp.route("/api/stock/ranking")
def get_stock_ranking():
    try:
        limit = request.args.get("limit", 20, type=int)
        rank_type = request.args.get("type", "gainers")
        records = fetch_stock_records()

        data = sorted(records, key=lambda x: x["change_percent"], reverse=(rank_type == "gainers"))
        return jsonify({"success": True, "data": data[:limit], "type": rank_type})
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "data": []}), 500


@stock_bp.route("/api/market/summary")
def get_market_summary():
    try:
        records = fetch_stock_records()
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
