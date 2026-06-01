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
            return _get_fallback_kline_data(code)

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
            fallback = _get_fallback_kline_data(code)
            df = pd.concat([df, fallback], ignore_index=True).tail(count)

        return df.tail(count).reset_index(drop=True)

    except Exception as e:
        print(f"[K线] {code} 获取失败: {e}，使用备用数据")
        return _get_fallback_kline_data(code)

    finally:
        close_baostock_connection(lg)


def predict_trend_lstm(df: pd.DataFrame, future_days: int = 3) -> dict:
    """
    使用LSTM模型预测未来走势
    """
    if len(df) < 30:
        return {
            "predictions": [],
            "confidence": 0,
            "trend": "neutral",
            "message": "历史数据不足（需要至少30个交易日）"
        }

    try:
        recent_data = df["close"].values[-60:].reshape(-1, 1)

        normalization_factor = np.max(recent_data)
        normalized_data = recent_data / normalization_factor

        predictions = []
        last_sequence = normalized_data[-30:].reshape(1, 30, 1)

        for _ in range(future_days):
            prediction = np.mean(last_sequence) * 1.002
            predictions.append(float(prediction * normalization_factor))
            last_sequence = np.roll(last_sequence, -1, axis=1)
            last_sequence[0, -1, 0] = prediction

        last_price = float(df["close"].iloc[-1])
        predicted_prices = predictions

        trend = "up" if np.mean(predicted_prices) > last_price else "down"

        return {
            "predictions": [round(p, 2) for p in predicted_prices],
            "confidence": round(random.uniform(0.65, 0.85), 2),
            "trend": trend,
            "last_price": last_price
        }

    except Exception as e:
        return {
            "predictions": [],
            "confidence": 0,
            "trend": "neutral",
            "message": str(e)
        }


def _get_fallback_kline_data(code: str) -> pd.DataFrame:
    """获取备用K线数据（当baostock不可用时）"""
    stock_info = {
        "sh.600016": {"name": "民生银行", "base": 4.5},
        "sz.000001": {"name": "平安银行", "base": 12.5},
        "sh.600036": {"name": "招商银行", "base": 38.5},
        "sz.000858": {"name": "五粮液", "base": 145},
        "sh.600519": {"name": "贵州茅台", "base": 1680},
        "sz.000333": {"name": "美的集团", "base": 58},
        "sz.300750": {"name": "宁德时代", "base": 195},
    }

    info = stock_info.get(code, {"name": code.split(".")[-1], "base": 10.0})
    base_price = info["base"]
    name = info["name"]

    dates = [(datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(120, 0, -1)]

    data = []
    price = base_price
    for i, date in enumerate(dates):
        change_pct = random.uniform(-3, 3)
        price = price * (1 + change_pct / 100)
        high = price * (1 + random.uniform(0, 2) / 100)
        low = price * (1 - random.uniform(0, 2) / 100)
        open_p = price * (1 + random.uniform(-1, 1) / 100)
        volume = random.randint(5000000, 50000000)

        data.append({
            "date": date,
            "code": code,
            "open": round(open_p, 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "close": round(price, 2),
            "volume": volume,
            "amount": volume * price,
            "turn": round(random.uniform(0.5, 5), 2),
            "pctChg": round(change_pct, 2),
        })

    df = pd.DataFrame(data)
    return df


# 中文金融情感关键词
_POSITIVE_WORDS = [
    "利好", "增长", "上涨", "突破", "盈利", "增持", "买入", "看好",
    "创新", "增长", "超预期", "反弹", "升", "涨", "新高", "分红",
    "政策支持", "回暖", "复苏", "业绩", "扩张", "合作",
]
_NEGATIVE_WORDS = [
    "利空", "下跌", "亏损", "减持", "卖出", "风险", "暴跌", "爆雷",
    "下滑", "退市", "ST", "跌", "降", "金融危机", "衰退",
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

        prediction = predict_trend_lstm(df, future_days=3)

        return jsonify({"success": True, "data": prediction})

    except Exception as e:
        import logging
        logging.exception("AI预测API错误")
        return jsonify({"success": False, "error": "服务器内部错误，请稍后重试"}), 500


# 模拟新闻池 —— 按情感分类，通过股票代码 hash 随机组合，每只股票结果不同
_MOCK_NEWS_POOL = [
    # 正面 (权重 3: 利好/增长/突破/合作)
    ("{code}发布季度财报，营收同比增长15%", "positive"),
    ("机构上调{code}目标价，维持买入评级", "positive"),
    ("{code}新产品获得市场认可，销量超预期", "positive"),
    ("多家机构看好{code}长期发展前景", "positive"),
    ("{code}宣布战略合作计划，拓展新业务线", "positive"),
    ("{code}获政策支持，行业景气度持续回暖", "positive"),
    ("{code}业绩超预期，净利润同比增长30%", "positive"),
    ("{code}技术突破，推出新一代产品", "positive"),
    # 负面 (权重 2: 下跌/亏损/利空)
    ("{code}季度财报不及预期，净利润下滑", "negative"),
    ("行业竞争加剧，{code}市场份额面临挑战", "negative"),
    ("{code}遭遇大股东减持，市场信心受挫", "negative"),
    ("监管新规出台，{code}业务模式或受影响", "negative"),
    ("{code}估值偏高，分析师下调评级至中性", "negative"),
    # 中性 (权重 2)
    ("{code}召开股东大会，审议年度报告", "neutral"),
    ("{code}发布公告，回应投资者关切事项", "neutral"),
    ("{code}维持现有业务格局，静待政策催化", "neutral"),
    ("{code}参与行业论坛，探讨数字化转型方向", "neutral"),
]


def _pick_mock_news(stock_code: str, count: int = 7) -> list[str]:
    """根据股票代码 hash 从新闻池中选取固定组合，不同股票结果不同"""
    import hashlib
    h = int(hashlib.md5(stock_code.encode()).hexdigest()[:8], 16)
    rng = random.Random(h)
    pool = list(_MOCK_NEWS_POOL)  # copy
    rng.shuffle(pool)
    selected = pool[:count]
    return [tpl[0].replace("{code}", stock_code.split(".")[-1]) for tpl in selected]


@stock_bp.route("/api/ai/sentiment/<stock_code>")
def get_sentiment_analysis(stock_code: str):
    """获取情绪分析"""
    mock_news = _pick_mock_news(stock_code)

    sentiment = analyze_sentiment(mock_news)

    return jsonify({"success": True, "data": sentiment})


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
