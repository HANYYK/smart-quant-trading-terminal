"""
基金分析路由 - 天天基金网数据接口
增强版：新增Calmar比率、Sortino比率、Alpha、Beta、信息比率等高级指标
定投模拟器、资产配置分析、相关性分析等功能
"""
from flask import Blueprint, render_template, jsonify, request
import requests
import pandas as pd
import numpy as np
import json
import re
from datetime import datetime, timedelta
import logging

from utils import cached

logger = logging.getLogger(__name__)
fund_bp = Blueprint("fund", __name__)

# ==================== 常量定义（使用元组节省内存）====================
FUND_API_BASE = "http://fundgz.1234567.com.cn/js"

# 基金基础数据 - 使用元组节省内存 (code, name, type, risk, manager, scale)
_FALLBACK_FUNDS = (
    ("005827","易方达蓝筹精选混合","混合型","中高","张坤","300亿+"),
    ("006228","中欧医疗健康混合A","混合型","中高","葛兰","400亿+"),
    ("161725","招商中证白酒指数(LOF)A","指数型","中高","侯昊","500亿+"),
    ("110022","易方达消费行业股票","股票型","高","萧楠","200亿+"),
    ("000751","嘉实新兴产业股票","股票型","高","归凯","150亿+"),
    ("550018","信达澳银新能源产业股票","股票型","高","冯明远","200亿+"),
    ("001475","易方达国防军工混合","混合型","高","刘洋","100亿+"),
    ("270042","广发纳斯达克100指数A","QDII","高","李耀柱","50亿+"),
    ("420002","天弘余额宝货币","货币型","极低","王昌俊","10000亿+"),
    ("000198","天弘弘运宝货币A","货币型","极低","王昌俊","2000亿+"),
    ("515980","华泰柏瑞中证光伏产业ETF","指数型","高","李茜","60亿+"),
    ("512760","国泰CES芯片ETF","指数型","高","艾小军","80亿+"),
    ("000145","广发纯债债券A","债券型","低","张芊","50亿+"),
    ("159915","易方达创业板ETF","指数型","高","刘树荣","150亿+"),
    ("001714","工银文体产业股票A","股票型","高","袁芳","100亿+"),
)

# 排行榜数据 (code, name, 1y, 3y, 5y, 6m, 3m, 1m, sharpe, max_dd, vol, risk, theme)
_RANKINGS = {
    "stock": (("000751","嘉实新兴产业股票",45.2,120.5,185.6,18.5,8.2,2.5,1.85,32.5,28.5,"高","tech"),
              ("110022","易方达消费行业股票",38.7,98.3,156.8,15.2,6.8,1.8,1.62,35.8,25.2,"高","consume"),
              ("001714","工银文体产业股票",35.1,95.8,142.3,14.5,6.2,1.5,1.45,28.4,22.8,"高","consume"),
              ("550018","信达澳银新能源产业股票",42.8,115.6,168.5,18.2,8.5,2.8,1.78,35.5,30.2,"高","energy"),
              ("006228","中欧医疗健康混合A",32.8,110.5,165.2,13.5,5.8,1.4,1.72,30.2,26.5,"中高","medical"),
              ("512760","国泰CES芯片ETF",28.6,72.4,125.8,12.5,5.5,1.6,1.35,42.1,35.2,"高","tech"),
              ("159915","易方达创业板ETF",18.3,45.2,68.5,8.5,3.8,0.8,0.98,38.2,32.5,"高","tech")),
    "mix": (("005827","易方达蓝筹精选混合",42.5,135.2,195.8,17.5,7.8,2.2,1.95,28.6,24.5,"中高","consume"),
            ("001875","安信新回报混合",28.9,98.7,142.5,12.2,5.2,1.3,1.58,22.4,18.5,"中","tech"),
            ("163402","兴全趋势投资混合",25.3,85.6,125.8,10.8,4.5,1.0,1.42,24.8,20.2,"中","finance")),
    "index": (("161725","招商中证白酒指数",52.3,185.6,285.5,22.5,10.5,3.2,2.15,42.8,38.5,"中高","consume"),
              ("270042","广发纳斯达克100",35.6,78.9,125.8,15.2,6.8,2.0,1.48,28.3,25.5,"高","tech"),
              ("515980","华泰柏瑞中证光伏产业ETF",38.5,85.5,125.5,16.5,7.5,2.2,1.65,45.5,35.5,"高","energy")),
    "bond": (("000145","广发纯债债券",5.2,15.8,25.5,2.2,1.0,0.3,1.85,2.5,3.5,"低","finance"),
             ("000104","华安可转债债券",8.5,25.6,42.5,3.8,1.6,0.4,1.95,12.5,12.5,"中高","finance")),
    "money": (("420002","天弘余额宝货币",2.1,6.8,11.5,0.9,0.45,0.15,2.85,0,0.5,"极低","finance"),
              ("000198","天弘弘运宝货币",2.15,6.95,11.8,0.92,0.46,0.15,2.92,0,0.5,"极低","finance")),
    "qdii": (("270042","广发纳斯达克100",35.6,78.9,125.8,15.2,6.8,2.0,1.48,28.3,25.5,"高","tech"),
             ("513500","博时标普500ETF联接",25.8,65.3,98.5,11.2,4.8,1.2,1.35,25.6,20.5,"中","finance")),
}

def _fmt_fund(item):
    """格式化基金数据"""
    return {"fund_code":item[0],"fund_name":item[1],"fund_type":item[2],"risk":item[3],"manager":item[4],"scale":item[5]}

def _fmt_ranking(item):
    """格式化排行榜数据"""
    return {"fund_code":item[0],"fund_name":item[1],"1y":item[2],"3y":item[3],"5y":item[4],"6m":item[5],
            "3m":item[6],"1m":item[7],"sharpe":item[8],"max_drawdown":item[9],"volatility":item[10],
            "risk":item[11],"theme":item[12],"tags":[]}


def _lookup_local_fund(fund_code: str) -> dict:
    for item in _FALLBACK_FUNDS:
        if item[0] == fund_code:
            return _fmt_fund(item)
    for ranking_items in _RANKINGS.values():
        for item in ranking_items:
            if item[0] == fund_code:
                return {
                    "fund_code": item[0],
                    "fund_name": item[1],
                    "fund_type": guess_type(item[1]),
                    "risk": item[11],
                    "manager": "",
                    "scale": "",
                }
    return {}

_session = requests.Session()
_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "http://fund.eastmoney.com/"
})

# ==================== 公共工具函数 ====================
def parse_jsonp(content):
    match = re.search(r"jsonpgz\(\{(.+?)\}\)", content, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(("{" + match.group(1) + "}").replace("None","null").replace("True","true").replace("False","false"))
    except:
        return None

def api_resp(success, data=None, error=None):
    r = {"success": success}
    if data is not None: r["data"] = data
    if error: r["error"] = error
    return r



def guess_type(name):
    if any(k in name for k in ["指数","ETF","联接"]): return "指数型"
    if "货币" in name: return "货币型"
    if any(k in name for k in ["债券","纯债","信用债"]): return "债券型"
    if any(k in name for k in ["QDII","海外","纳斯达克"]): return "QDII"
    if "股票" in name: return "股票型"
    return "混合型"


_INVALID_FUND_NAME_KEYWORDS = (
    "郑重声明",
    "天天基金网发布",
    "与本网站立场无关",
    "不保证该信息",
    "投资决策建议",
    "风险自担",
    "数据来源",
    "东方财富Choice数据",
)


def _clean_html_text(value: str) -> str:
    """Clean text scraped from fund pages."""
    if not value:
        return ""
    value = re.sub(r"<[^>]+>", "", str(value))
    value = re.sub(r"\s+", " ", value)
    return value.strip(" \t\r\n:：")


def _is_valid_fund_name(name: str, fund_code: str = "") -> bool:
    """Reject page disclaimers and other non-name text."""
    name = _clean_html_text(name)
    if not name:
        return False
    if fund_code and name == fund_code:
        return False
    if len(name) > 80:
        return False
    if any(keyword in name for keyword in _INVALID_FUND_NAME_KEYWORDS):
        return False
    return True


@cached(ttl=3600)
def search_funds_from_api(keyword: str, search_type: str = "all") -> list:
    """从东方财富搜索真实基金数据"""
    try:
        url = "https://suggest3.eastmoney.com/sug"
        params = {"type": "fund", "key": keyword, "count": 100, "_": int(datetime.now().timestamp() * 1000)}
        response = _session.get(url, params=params, timeout=3)  # 缩短超时到3秒

        if response.status_code != 200:
            return []

        text = response.text.strip()
        # 检查返回的是否是JSON（不是HTML）
        if not text or not text.startswith('{'):
            return []

        data = json.loads(text)
        if not isinstance(data, dict) or "q" not in data:
            return []

        results = []
        for item in data.get("q", []):
            if isinstance(item, list) and len(item) >= 2:
                code, name = str(item[0]), str(item[1])
                if code and name:
                    results.append({"fund_code": code, "fund_name": name, "fund_type": guess_type(name), "risk": "中", "manager": "", "scale": ""})
        return results
    except Exception as e:
        logger.warning(f"基金搜索API错误: {e}")
        return []  # 快速降级到本地数据


def verify_fund_by_realtime_api(fund_code: str) -> dict:
    """通过实时估值API验证基金代码"""
    try:
        response = _session.get(f"{FUND_API_BASE}/{fund_code}.js", timeout=3)
        if response.status_code != 200:
            return api_resp(False, error="基金不存在")

        data = parse_jsonp(response.text)
        if not data:
            return api_resp(False, error="基金不存在")

        fund_name = _clean_html_text(data.get("name", ""))
        if not _is_valid_fund_name(fund_name, fund_code):
            fund_name = ""
        return api_resp(True, {
            "fund_code": data.get("fundcode", fund_code),
            "fund_name": fund_name,
            "fund_type": guess_type(fund_name),
            "risk": "中", "manager": "", "scale": "",
        })
    except Exception as e:
        return api_resp(False, error=str(e))


def _map_risk_level(risk_str: str) -> str:
    """映射风险等级"""
    risk_map = {
        "1": "极低",
        "2": "低",
        "3": "中低",
        "4": "中",
        "5": "中高",
        "6": "高",
        "R1": "极低",
        "R2": "低",
        "R3": "中",
        "R4": "中高",
        "R5": "高",
    }
    return risk_map.get(str(risk_str), "中")


def _format_scale(scale: float) -> str:
    """格式化基金规模"""
    if not scale or scale <= 0:
        return "未知"
    if scale >= 10000:
        return f"{scale/10000:.1f}万亿"
    elif scale >= 100:
        return f"{scale:.0f}亿"
    else:
        return f"{scale:.1f}亿"


@cached(ttl=30)
def fetch_fund_realtime_data(fund_code: str) -> dict:
    """获取基金实时估值数据"""
    try:
        response = _session.get(f"{FUND_API_BASE}/{fund_code}.js", timeout=5)
        if response.status_code != 200:
            return api_resp(False, error="请求失败")
        
        text = response.text
        if not text or len(text) < 10:
            return api_resp(False, error="数据为空")

        data = parse_jsonp(text)
        if not data:
            return api_resp(False, error="数据解析失败")

        return api_resp(True, {
            "fund_code": data.get("fundcode", ""),
            "fund_name": _clean_html_text(data.get("name", "")) if _is_valid_fund_name(data.get("name", ""), fund_code) else "",
            "net_value": float(data.get("dwjz", 0)) if data.get("dwjz") else 0,
            "estimate_value": float(data.get("gsz", 0)) if data.get("gsz") else 0,
            "estimate_change": float(data.get("gszzl", 0)) if data.get("gszzl") else 0,
            "update_date": data.get("gztime", ""),
        })
    except Exception as e:
        return api_resp(False, error=str(e))


@cached(ttl=21600)
def fetch_fund_history(fund_code: str, days: int = 365) -> dict:
    """获取基金历史净值"""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    try:
        from akshare import fund

        df = None
        try:
            df = fund.fund_open_fund_info_em(
                symbol=fund_code,
                indicator="单位净值走势",
            )
        except TypeError:
            df = fund.fund_open_fund_info_em(
                fund_code,
                start_date.strftime("%Y%m%d"),
                end_date.strftime("%Y%m%d"),
            )

        if df is not None and not df.empty:
            date_col = "日期" if "日期" in df.columns else "净值日期"
            if date_col in df.columns:
                df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
                df = df[(df[date_col] >= start_date) & (df[date_col] <= end_date)]
                df = df.sort_values(date_col)

            history_data = _normalize_fund_history_frame(df)
            if history_data:
                return {"success": True, "data": history_data}
    except Exception as e:
        logger.warning(f"akshare fund history failed for {fund_code}: {e}")

    return fetch_fund_history_from_eastmoney(fund_code, days)


def _normalize_fund_history_frame(df: pd.DataFrame) -> list:
    """Convert akshare fund history data to the frontend schema."""
    history_data = []
    date_col = "日期" if "日期" in df.columns else "净值日期"

    for _, row in df.iterrows():
        net_value = _to_float(row.get("单位净值"))
        acc_value = _to_float(row.get("累计净值"), net_value)
        date_value = row.get(date_col, "")

        if pd.isna(date_value) or net_value <= 0:
            continue

        if hasattr(date_value, "strftime"):
            date_text = date_value.strftime("%Y-%m-%d")
        else:
            date_text = str(date_value)[:10]

        history_data.append({
            "date": date_text,
            "net_value": round(net_value, 4),
            "累计净值": round(acc_value, 4),
        })

    return history_data


def _to_float(value, default: float = 0) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        value_text = str(value).strip().replace(",", "").replace("%", "")
        if value_text in ("", "--", "-"):
            return default
        return float(value_text)
    except Exception:
        return default


def _parse_history_date(value) -> datetime | None:
    """Parse date strings from fund/index data."""
    if value is None:
        return None
    if hasattr(value, "to_pydatetime"):
        return value.to_pydatetime()
    if hasattr(value, "strftime") and not isinstance(value, str):
        return value

    text = str(value).strip().replace("/", "-")
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%y-%m-%d"):
        try:
            return datetime.strptime(text[:10] if fmt != "%Y%m%d" else text[:8], fmt)
        except Exception:
            continue
    return None


def _sorted_history(history_data: list) -> list:
    return sorted(
        [d for d in history_data if _parse_history_date(d.get("date")) and _to_float(d.get("net_value")) > 0],
        key=lambda item: _parse_history_date(item.get("date")),
    )


def _calendar_years_between(start_date, end_date, fallback_points: int = 0) -> float:
    start = _parse_history_date(start_date)
    end = _parse_history_date(end_date)
    if start and end and end > start:
        return max((end - start).days / 365.25, 1 / 365.25)
    return max(fallback_points / 252, 1 / 365.25)


def _return_between(start_value: float, end_value: float) -> float:
    return ((end_value - start_value) / start_value * 100) if start_value > 0 else 0


def fetch_fund_history_from_eastmoney(fund_code: str, days: int = 365) -> dict:
    """Fetch fund NAV history directly from Eastmoney as a robust fallback."""
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        url = "https://api.fund.eastmoney.com/f10/lsjz"
        params = {
            "fundCode": fund_code,
            "pageIndex": 1,
            "pageSize": min(max(days * 2, 120), 2000),
            "startDate": start_date.strftime("%Y-%m-%d"),
            "endDate": end_date.strftime("%Y-%m-%d"),
        }
        headers = {
            "Referer": f"https://fundf10.eastmoney.com/jjjz_{fund_code}.html",
            "User-Agent": _session.headers.get("User-Agent", "Mozilla/5.0"),
        }
        response = _session.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        payload = response.json()
        data_node = payload.get("Data") or {}
        records = data_node.get("LSJZList") or []

        history_data = []
        for item in reversed(records):
            net_value = _to_float(item.get("DWJZ"))
            acc_value = _to_float(item.get("LJJZ"), net_value)
            date_text = str(item.get("FSRQ", ""))[:10]
            if not date_text or net_value <= 0:
                continue
            history_data.append({
                "date": date_text,
                "net_value": round(net_value, 4),
                "累计净值": round(acc_value, 4),
            })

        if not history_data:
            return fetch_fund_history_from_f10_page(fund_code, days)

        return {"success": True, "data": history_data}
    except Exception as e:
        logger.error(f"Eastmoney fund history failed for {fund_code}: {e}")
        return fetch_fund_history_from_f10_page(fund_code, days)


def fetch_fund_history_from_f10_page(fund_code: str, days: int = 365) -> dict:
    """Fetch fund NAV history from Eastmoney's legacy F10 table endpoint."""
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        url = "https://fundf10.eastmoney.com/F10DataApi.aspx"
        params = {
            "type": "lsjz",
            "code": fund_code,
            "page": 1,
            "per": min(max(days * 2, 120), 2000),
            "sdate": start_date.strftime("%Y-%m-%d"),
            "edate": end_date.strftime("%Y-%m-%d"),
        }
        response = _session.get(url, params=params, timeout=10)
        response.raise_for_status()

        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", response.text, re.DOTALL)
        history_data = []
        for row in rows:
            cells = [
                _clean_html_text(re.sub(r"<[^>]+>", "", cell))
                for cell in re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
            ]
            if len(cells) < 3 or not re.match(r"\d{4}-\d{2}-\d{2}", cells[0]):
                continue

            net_value = _to_float(cells[1])
            acc_value = _to_float(cells[2], net_value)
            if net_value <= 0:
                continue

            history_data.append({
                "date": cells[0],
                "net_value": round(net_value, 4),
                "累计净值": round(acc_value, 4),
            })

        history_data.sort(key=lambda item: item["date"])
        if not history_data:
            return {"success": False, "error": "无法获取历史数据"}

        return {"success": True, "data": history_data}
    except Exception as e:
        logger.error(f"Eastmoney F10 fund history failed for {fund_code}: {e}")
        return {"success": False, "error": str(e)}


@cached(ttl=86400)
def fetch_fund_holdings(fund_code: str) -> dict:
    """获取基金重仓持股"""
    try:
        url = "https://fundf10.eastmoney.com/FundArchivesDatas.aspx"
        params = {
            "type": "jjcc",
            "code": fund_code,
            "topline": "20",
            "year": datetime.now().year if datetime.now().month > 1 else datetime.now().year - 1,
            "month": datetime.now().month - 1 if datetime.now().month > 1 else 12
        }

        response = _session.get(url, params=params, timeout=10)
        if response.status_code != 200:
            return {"success": False, "error": "请求失败"}

        content = response.text
        holdings = []
        stock_pattern = r'<td>([\d\.]+)</td><td>([^<]+)</td><td>([^<]+)</td><td>([^<]+)</td>'
        matches = re.findall(stock_pattern, content)

        for match in matches[:10]:
            holdings.append({
                "rank": len(holdings) + 1,
                "stock_code": match[0],
                "stock_name": match[1],
                "shares": match[2],
                "value": match[3]
            })

        return {"success": True, "data": holdings}
    except Exception as e:
        return {"success": False, "error": str(e)}


@cached(ttl=86400)
def fetch_fund_info(fund_code: str) -> dict:
    """获取基金详细信息"""
    try:
        url = f"https://fundf10.eastmoney.com/jbgk_{fund_code}.html"
        response = _session.get(url, timeout=10)
        
        if response.status_code != 200:
            return {"success": False, "error": "请求失败"}

        content = response.text

        info = {
            "fund_code": fund_code,
            "fund_type": "",
            "fund_name": "",
            "establish_date": "",
            "manager": "",
            "fund_scale": "",
            "registration": "",
            "risk_level": "",
            "fee": "",
        }

        patterns = {
            "fund_name": r'基金全称.*?<div[^>]*>([^<]+)</div>',
            "fund_type": r'基金类型.*?<div[^>]*>([^<]+)</div>',
            "establish_date": r'成立日期.*?<div[^>]*>([^<]+)</div>',
            "manager": r'基金经理.*?<a[^>]*>([^<]+)</a>',
            "fund_scale": r'基金规模.*?<div[^>]*>([^<]+)</div>',
            "registration": r'备案机构.*?<div[^>]*>([^<]+)</div>',
            "risk_level": r'风险等级.*?<div[^>]*>([^<]+)</div>',
            "fee": r'最高费率.*?<div[^>]*>([^<]+)</div>',
        }

        for key, pattern in patterns.items():
            match = re.search(pattern, content, re.DOTALL)
            if match:
                value = _clean_html_text(match.group(1))
                if key == "fund_name" and not _is_valid_fund_name(value, fund_code):
                    continue
                info[key] = value

        _fill_fund_info_fallbacks(fund_code, info)
        return {"success": True, "data": info}
    except Exception as e:
        info = {
            "fund_code": fund_code,
            "fund_type": "",
            "fund_name": "",
            "establish_date": "",
            "manager": "",
            "fund_scale": "",
            "registration": "",
            "risk_level": "",
            "fee": "",
        }
        _fill_fund_info_fallbacks(fund_code, info)
        return {"success": True, "data": info, "warning": str(e)}


def _fill_fund_info_fallbacks(fund_code: str, info: dict) -> None:
    local = _lookup_local_fund(fund_code)
    realtime = fetch_fund_realtime_data(fund_code)
    realtime_data = realtime.get("data", {}) if realtime.get("success") else {}
    fund_name = info.get("fund_name") or realtime_data.get("fund_name") or local.get("fund_name") or ""

    info["fund_name"] = fund_name
    info["fund_type"] = info.get("fund_type") or local.get("fund_type") or guess_type(fund_name)
    info["risk_level"] = info.get("risk_level") or local.get("risk") or _map_risk_level("")
    info["manager"] = info.get("manager") or local.get("manager", "")
    info["fund_scale"] = info.get("fund_scale") or local.get("scale", "")


def calculate_performance_metrics(history_data: list) -> dict:
    """计算基金业绩指标"""
    if not history_data or len(history_data) < 2:
        return {
            "total_return": 0,
            "annualized_return": 0,
            "max_drawdown": 0,
            "sharpe_ratio": 0,
            "volatility": 0,
            "win_rate": 0,
        }

    try:
        history_data = _sorted_history(history_data)
        history_data = _sorted_history(history_data)
        net_values = [d["net_value"] for d in history_data]
        dates = [d["date"] for d in history_data]

        start_value = net_values[0]
        end_value = net_values[-1]

        total_return = _return_between(start_value, end_value)

        years = _calendar_years_between(dates[0], dates[-1], len(net_values) - 1)
        if years > 0 and start_value > 0:
            annualized_return = ((end_value / start_value) ** (1 / years) - 1) * 100
        else:
            annualized_return = 0
        calendar_days = max(1, round(years * 365.25))

        peak = net_values[0]
        max_dd = 0
        for value in net_values:
            if value > peak:
                peak = value
            drawdown = (peak - value) / peak * 100
            if drawdown > max_dd:
                max_dd = drawdown

        returns = []
        for i in range(1, len(net_values)):
            if net_values[i-1] > 0:
                ret = (net_values[i] - net_values[i-1]) / net_values[i-1]
                returns.append(ret)

        volatility = np.std(returns) * np.sqrt(252) * 100 if len(returns) > 1 else 0

        if len(returns) > 0 and volatility > 0:
            mean_return = np.mean(returns) * 252
            sharpe_ratio = mean_return / (volatility / 100)
        else:
            sharpe_ratio = 0

        winning_days = sum(1 for r in returns if r > 0)
        win_rate = (winning_days / len(returns) * 100) if len(returns) > 0 else 0

        return {
            "total_return": round(total_return, 2),
            "annualized_return": round(annualized_return, 2),
            "max_drawdown": round(max_dd, 2),
            "sharpe_ratio": round(sharpe_ratio, 2),
            "volatility": round(volatility, 2),
            "win_rate": round(win_rate, 2),
            "days": calendar_days,
            "points": len(net_values),
        }
    except Exception as e:
        logger.error(f"Performance calculation error: {e}")
        return {
            "total_return": 0,
            "annualized_return": 0,
            "max_drawdown": 0,
            "sharpe_ratio": 0,
            "volatility": 0,
            "win_rate": 0,
        }


def calculate_advanced_metrics(history_data: list, benchmark_data: list = None) -> dict:
    """计算高级业绩指标：Calmar比率、Sortino比率、Alpha、Beta、信息比率等"""
    if not history_data or len(history_data) < 10:
        return {
            "calmar_ratio": 0,
            "sortino_ratio": 0,
            "alpha": 0,
            "beta": 0,
            "information_ratio": 0,
            "tracking_error": 0,
            "downside_deviation": 0,
            "value_at_risk": 0,
            "conditional_var": 0,
            "omega_ratio": 0,
            "tail_ratio": 0,
        }

    try:
        net_values = [d["net_value"] for d in history_data]
        dates = [d["date"] for d in history_data]

        returns = []
        for i in range(1, len(net_values)):
            if net_values[i-1] > 0:
                ret = (net_values[i] - net_values[i-1]) / net_values[i-1]
                returns.append(ret)

        if len(returns) < 5:
            return {
                "calmar_ratio": 0, "sortino_ratio": 0, "alpha": 0, "beta": 0,
                "information_ratio": 0, "tracking_error": 0, "downside_deviation": 0,
                "value_at_risk": 0, "conditional_var": 0, "omega_ratio": 0, "tail_ratio": 0,
            }

        returns_array = np.array(returns)

        total_return = (net_values[-1] - net_values[0]) / net_values[0]
        years = _calendar_years_between(dates[0], dates[-1], len(returns))
        annualized_return = (net_values[-1] / net_values[0]) ** (1 / years) - 1 if years > 0 else 0

        peak = net_values[0]
        max_dd = 0
        for value in net_values:
            if value > peak:
                peak = value
            drawdown = (peak - value) / peak
            if drawdown > max_dd:
                max_dd = drawdown

        volatility = np.std(returns_array) * np.sqrt(252) if len(returns_array) > 1 else 0
        mean_return = np.mean(returns_array) * 252

        calmar_ratio = annualized_return / max_dd if max_dd > 0 else 0

        downside_returns = returns_array[returns_array < 0]
        downside_std = np.std(downside_returns) * np.sqrt(252) if len(downside_returns) > 1 else 0
        sortino_ratio = annualized_return / downside_std if downside_std > 0 else 0

        alpha, beta = 0, 1
        tracking_error, information_ratio = 0, 0

        if benchmark_data and len(benchmark_data) > 10:
            aligned = _aligned_daily_returns(history_data, benchmark_data)
            benchmark_returns = [item[1] for item in aligned]
            aligned_returns = [item[0] for item in aligned]

            min_len = min(len(aligned_returns), len(benchmark_returns))
            if min_len > 5:
                fund_ret = np.array(aligned_returns[:min_len])
                bench_ret = np.array(benchmark_returns[:min_len])

                covariance = np.cov(fund_ret, bench_ret)[0, 1]
                bench_variance = np.var(bench_ret)
                beta = covariance / bench_variance if bench_variance > 0 else 1

                risk_free = 0.03 / 252
                fund_excess = fund_ret - risk_free
                bench_excess = bench_ret - risk_free

                alpha = (np.mean(fund_excess) - beta * np.mean(bench_excess)) * 252

                active_returns = fund_ret - bench_ret
                tracking_error = np.std(active_returns) * np.sqrt(252)
                information_ratio = np.mean(active_returns) * 252 / tracking_error if tracking_error > 0 else 0

        var_95 = np.percentile(returns_array, 5)
        cvar_95 = np.mean(returns_array[returns_array <= var_95]) if len(returns_array[returns_array <= var_95]) > 0 else var_95

        positive_returns = returns_array[returns_array > 0]
        negative_returns = abs(returns_array[returns_array < 0])
        tail_ratio = np.sum(positive_returns) / np.sum(negative_returns) if np.sum(negative_returns) > 0 else 0

        threshold = 0
        gains = returns_array[returns_array > threshold] - threshold
        losses = threshold - returns_array[returns_array <= threshold]
        omega = np.sum(gains) / np.sum(losses) if np.sum(losses) > 0 else 0

        return {
            "calmar_ratio": round(calmar_ratio, 2),
            "sortino_ratio": round(sortino_ratio, 2),
            "alpha": round(alpha * 100, 2),
            "beta": round(beta, 2),
            "information_ratio": round(information_ratio, 2),
            "tracking_error": round(tracking_error * 100, 2),
            "downside_deviation": round(downside_std * 100, 2),
            "value_at_risk": round(var_95 * 100, 2),
            "conditional_var": round(cvar_95 * 100, 2),
            "omega_ratio": round(omega, 2),
            "tail_ratio": round(tail_ratio, 2),
        }
    except Exception as e:
        logger.error(f"Advanced metrics calculation error: {e}")
        return {
            "calmar_ratio": 0, "sortino_ratio": 0, "alpha": 0, "beta": 0,
            "information_ratio": 0, "tracking_error": 0, "downside_deviation": 0,
            "value_at_risk": 0, "conditional_var": 0, "omega_ratio": 0, "tail_ratio": 0,
        }


def calculate_period_returns(history_data: list) -> dict:
    """计算不同时间段的收益"""
    if not history_data:
        return {}

    try:
        history_data = _sorted_history(history_data)
        if len(history_data) < 2:
            return {}

        net_values = [d["net_value"] for d in history_data]
        dates = [_parse_history_date(d["date"]) for d in history_data]

        def calc_return(start_idx, end_idx=None):
            end_idx = len(net_values) - 1 if end_idx is None else end_idx
            if start_idx < 0 or start_idx >= len(net_values) or end_idx >= len(net_values):
                return 0
            return _return_between(net_values[start_idx], net_values[end_idx])

        def find_start_by_calendar(days_back: int) -> int:
            target = dates[-1] - timedelta(days=days_back)
            candidate = 0
            for idx, item_date in enumerate(dates):
                if item_date and item_date <= target:
                    candidate = idx
                else:
                    break
            return candidate

        period_returns = {
            "1w": 0, "1m": 0, "3m": 0, "6m": 0,
            "1y": 0, "2y": 0, "3y": 0, "5y": 0,
            "since_year": {}
        }

        spans = {
            "1w": 7,
            "1m": 30,
            "3m": 90,
            "6m": 180,
            "1y": 365,
            "2y": 365 * 2,
            "3y": 365 * 3,
            "5y": 365 * 5,
        }
        for key, span_days in spans.items():
            if dates[-1] and dates[0] and (dates[-1] - dates[0]).days >= min(span_days * 0.7, span_days):
                period_returns[key] = round(calc_return(find_start_by_calendar(span_days)), 2)

        current_year = dates[-1].year if dates[-1] else datetime.now().year
        this_year_start = next((i for i, d in enumerate(dates) if d and d.year == current_year), None)
        if this_year_start is not None:
            period_returns["since_year"]["this_year"] = {
                "start": net_values[this_year_start],
                "start_date": history_data[this_year_start]["date"],
                "end": net_values[-1],
                "return": round(calc_return(this_year_start), 2),
            }

        last_year_indices = [i for i, d in enumerate(dates) if d and d.year == current_year - 1]
        if last_year_indices:
            start_idx = last_year_indices[0]
            end_idx = last_year_indices[-1]
            period_returns["since_year"]["last_year"] = {
                "start": net_values[start_idx],
                "start_date": history_data[start_idx]["date"],
                "end": net_values[end_idx],
                "return": round(calc_return(start_idx, end_idx), 2),
            }

        return period_returns
    except Exception as e:
        logger.error(f"Period returns calculation error: {e}")
        return {}


def simulate_fixed_investment(history_data: list, monthly_amount: float = 1000) -> dict:
    """定投模拟器"""
    if not history_data or len(history_data) < 30:
        return {
            "success": False,
            "error": "数据不足，无法进行定投模拟"
        }

    try:
        total_invested = 0
        total_units = 0
        monthly_records = []

        history_data = _sorted_history(history_data)
        net_values = [d["net_value"] for d in history_data]
        dates = [d["date"] for d in history_data]

        monthly_investments = []
        seen_months = set()

        for i, date_text in enumerate(dates):
            item_date = _parse_history_date(date_text)
            if not item_date:
                continue
            month_key = item_date.strftime("%Y-%m")
            if month_key in seen_months:
                continue
            seen_months.add(month_key)
            monthly_investments.append({
                "index": i,
                "nav": net_values[i],
                "date": dates[i],
            })

        monthly_investments = monthly_investments[-60:]
        cash_flows = []

        for month_data in monthly_investments:
            nav = month_data["nav"]
            if nav > 0:
                units = monthly_amount / nav
                total_invested += monthly_amount
                total_units += units
                cash_flows.append((_parse_history_date(month_data["date"]), -monthly_amount))

                current_value = total_units * nav
                profit = current_value - total_invested
                profit_rate = (profit / total_invested * 100) if total_invested > 0 else 0

                monthly_records.append({
                    "date": month_data["date"],
                    "invested": round(total_invested, 2),
                    "value": round(current_value, 2),
                    "profit": round(profit, 2),
                    "profit_rate": round(profit_rate, 2),
                    "units": round(total_units, 2),
                })

        if not monthly_records:
            return {"success": False, "error": "数据不足"}

        final_record = monthly_records[-1]
        final_value = total_units * net_values[-1]
        total_profit = final_value - total_invested
        total_profit_rate = (total_profit / total_invested * 100) if total_invested > 0 else 0

        months_count = len(monthly_records)
        cash_flows.append((_parse_history_date(dates[-1]), final_value))
        annual_return = _xirr(cash_flows) * 100 if len(cash_flows) >= 3 else 0

        return {
            "success": True,
            "data": {
                "total_invested": round(total_invested, 2),
                "total_value": round(final_value, 2),
                "total_profit": round(total_profit, 2),
                "total_profit_rate": round(total_profit_rate, 2),
                "annual_return": round(annual_return, 2),
                "total_units": round(total_units, 2),
                "current_nav": net_values[-1],
                "monthly_amount": monthly_amount,
                "months": months_count,
                "records": monthly_records[-24:] if len(monthly_records) > 24 else monthly_records,
            }
        }
    except Exception as e:
        logger.error(f"Fixed investment simulation error: {e}")
        return {"success": False, "error": str(e)}


def calculate_correlation_with_index(history_data: list, index_code: str = "000300") -> dict:
    """计算与指数的相关性分析"""
    if not history_data or len(history_data) < 2:
        return {"success": False, "error": "数据不足"}

    try:
        index_data = fetch_index_data(index_code, 365)
        if not index_data["success"]:
            history_data = _sorted_history(history_data)
            fund_values = [d["net_value"] for d in history_data]
            fund_total = _return_between(fund_values[0], fund_values[-1]) if len(fund_values) >= 2 else 0
            return {
                "success": True,
                "data": {
                    "correlation": 0,
                    "interpretation": "指数数据暂不可用，无法计算相关性",
                    "fund_total_return": round(fund_total, 2),
                    "index_total_return": 0,
                    "excess_return": round(fund_total, 2),
                    "beta": 0,
                    "r_squared": 0,
                    "sample_size": 0,
                }
            }

        history_data = _sorted_history(history_data)
        index_history = index_data["data"]
        aligned = _aligned_daily_returns(history_data, index_history)
        fund_returns = [item[0] for item in aligned]
        index_returns = [item[1] for item in aligned]

        min_len = min(len(fund_returns), len(index_returns))
        if min_len < 2:
            fund_values = [d["net_value"] for d in history_data]
            index_history = index_data["data"]
            index_values = [d["value"] for d in index_history if _parse_history_date(d.get("date"))]
            fund_total = _return_between(fund_values[0], fund_values[-1]) if len(fund_values) >= 2 else 0
            index_total = _return_between(index_values[0], index_values[-1]) if len(index_values) >= 2 else 0
            return {
                "success": True,
                "data": {
                    "correlation": 0,
                    "interpretation": "同日数据不足，暂无法计算稳定相关性",
                    "fund_total_return": round(fund_total, 2),
                    "index_total_return": round(index_total, 2),
                    "excess_return": round(fund_total - index_total, 2),
                    "beta": 0,
                    "r_squared": 0,
                    "sample_size": min_len,
                }
            }

        correlation = np.corrcoef(fund_returns[:min_len], index_returns[:min_len])[0, 1]
        if np.isnan(correlation):
            correlation = 0

        fund_values = [d["net_value"] for d in history_data]
        index_values = [d["value"] for d in index_history if _parse_history_date(d.get("date"))]
        fund_cum_ret = [(f - fund_values[0]) / fund_values[0] * 100 for f in fund_values] if fund_values and fund_values[0] > 0 else []
        index_cum_ret = [(i - index_values[0]) / index_values[0] * 100 for i in index_values] if index_values and index_values[0] > 0 else []

        excess_returns = [f - i for f, i in zip(fund_cum_ret[:min_len], index_cum_ret[:min_len])]

        return {
            "success": True,
            "data": {
                "correlation": round(correlation, 3),
                "interpretation": _interpret_correlation(correlation),
                "fund_total_return": round(fund_cum_ret[-1] if fund_cum_ret else 0, 2),
                "index_total_return": round(index_cum_ret[-1] if index_cum_ret else 0, 2),
                "excess_return": round(excess_returns[-1] if excess_returns else 0, 2),
                "beta": round(correlation, 2),
                "r_squared": round(correlation ** 2, 3),
                "sample_size": min_len,
            }
        }
    except Exception as e:
        logger.error(f"Correlation analysis error: {e}")
        return {"success": False, "error": str(e)}


def _aligned_daily_returns(fund_history: list, benchmark_history: list) -> list:
    """Align fund and benchmark daily returns by actual date."""
    def to_series(items, value_key):
        series = {}
        for item in items:
            item_date = _parse_history_date(item.get("date"))
            value = _to_float(item.get(value_key))
            if item_date and value > 0:
                series[item_date.strftime("%Y-%m-%d")] = value
        return series

    fund_series = to_series(fund_history, "net_value")
    bench_series = to_series(benchmark_history, "value")
    common_dates = sorted(set(fund_series) & set(bench_series))
    aligned = []

    for prev_date, curr_date in zip(common_dates, common_dates[1:]):
        prev_fund = fund_series[prev_date]
        prev_bench = bench_series[prev_date]
        if prev_fund <= 0 or prev_bench <= 0:
            continue
        aligned.append((
            (fund_series[curr_date] - prev_fund) / prev_fund,
            (bench_series[curr_date] - prev_bench) / prev_bench,
        ))

    return aligned


def _xirr(cash_flows: list) -> float:
    """Approximate annualized money-weighted return for irregular cash flows."""
    flows = [(date, amount) for date, amount in cash_flows if date is not None and amount]
    if len(flows) < 2 or not any(amount < 0 for _, amount in flows) or not any(amount > 0 for _, amount in flows):
        return 0

    start_date = flows[0][0]

    def npv(rate):
        total = 0
        for date, amount in flows:
            years = max((date - start_date).days / 365.25, 0)
            total += amount / ((1 + rate) ** years)
        return total

    low, high = -0.95, 5.0
    for _ in range(80):
        mid = (low + high) / 2
        value = npv(mid)
        if abs(value) < 1e-7:
            return mid
        if value > 0:
            low = mid
        else:
            high = mid

    return (low + high) / 2


def _interpret_correlation(r: float) -> str:
    """解释相关性系数"""
    abs_r = abs(r)
    if abs_r >= 0.9:
        strength = "非常强"
    elif abs_r >= 0.7:
        strength = "强"
    elif abs_r >= 0.5:
        strength = "中等"
    elif abs_r >= 0.3:
        strength = "弱"
    else:
        strength = "非常弱"

    direction = "正" if r > 0 else "负"
    return f"{strength}{direction}相关"


@cached(ttl=86400)
def fetch_fund_asset_allocation(fund_code: str) -> dict:
    """获取基金资产配置"""
    try:
        url = f"https://fundf10.eastmoney.com/FundArchivesDatas.aspx"
        params = {
            "type": "zcpz",
            "code": fund_code,
        }
        response = _session.get(url, params=params, timeout=10)
        if response.status_code != 200:
            return {"success": False, "error": "请求失败"}

        content = response.text
        allocations = []

        patterns = [
            (r'股票.*?(\d+\.?\d*)%', '股票'),
            (r'债券.*?(\d+\.?\d*)%', '债券'),
            (r'现金.*?(\d+\.?\d*)%', '现金'),
            (r'银行存款.*?(\d+\.?\d*)%', '银行存款'),
            (r'其他.*?(\d+\.?\d*)%', '其他'),
        ]

        for pattern, asset_type in patterns:
            match = re.search(pattern, content)
            if match:
                value = float(match.group(1))
                if value > 0:
                    allocations.append({
                        "type": asset_type,
                        "ratio": value,
                    })

        if not allocations:
            allocations = _infer_asset_allocation(fund_code)

        return {"success": True, "data": allocations}
    except Exception as e:
        return {"success": True, "data": _infer_asset_allocation(fund_code), "warning": str(e)}


def _infer_asset_allocation(fund_code: str) -> list:
    info = fetch_fund_info(fund_code).get("data", {})
    fund_type = info.get("fund_type") or guess_type(info.get("fund_name", ""))
    if "货币" in fund_type:
        return [{"type": "现金", "ratio": 100.0}]
    if "债券" in fund_type:
        return [{"type": "债券", "ratio": 85.0}, {"type": "现金", "ratio": 15.0}]
    if "指数" in fund_type or "股票" in fund_type or "ETF" in info.get("fund_name", ""):
        return [{"type": "股票", "ratio": 90.0}, {"type": "现金", "ratio": 10.0}]
    return [{"type": "股票", "ratio": 60.0}, {"type": "债券", "ratio": 25.0}, {"type": "现金", "ratio": 15.0}]


@cached(ttl=86400)
def fetch_fund_manager_info(fund_code: str) -> dict:
    """获取基金经理详细信息"""
    try:
        url = f"https://fundf10.eastmoney.com/Manager/{fund_code}.html"
        response = _session.get(url, timeout=10)

        if response.status_code != 200:
            return {"success": False, "error": "请求失败"}

        content = response.text

        patterns = {
            "name": r'经理名称.*?<a[^>]*>([^<]+)</a>',
            "tenure": r'任职期间.*?(\d{4}-\d{4})',
            "term_return": r'任职回报.*?([+-]?\d+\.?\d*)%',
        }

        info = {"name": "", "tenure": "", "term_return": ""}
        for key, pattern in patterns.items():
            match = re.search(pattern, content)
            if match:
                info[key] = match.group(1).strip()

        return {"success": True, "data": info}
    except Exception as e:
        return {"success": False, "error": str(e)}


def fetch_fund_dividend_history(fund_code: str) -> dict:
    """获取基金分红历史"""
    try:
        url = f"https://fundf10.eastmoney.com/fhsp_{fund_code}.html"
        response = _session.get(url, timeout=10)

        if response.status_code != 200:
            return {"success": False, "error": "请求失败"}

        content = response.text
        dividends = []

        pattern = r'<td>(\d{4}-\d{2}-\d{2})</td><td>(\d+\.?\d*)</td><td>(\d+\.?\d*)</td>'
        matches = re.findall(pattern, content)

        for match in matches[:20]:
            dividends.append({
                "date": match[0],
                "dividend_per_unit": float(match[1]),
                "nav_before": float(match[2]),
            })

        return {"success": True, "data": dividends}
    except Exception as e:
        return {"success": False, "error": str(e)}


@cached(ttl=86400)
def fetch_fund_risk_metrics(fund_code: str) -> dict:
    """获取基金风险评级"""
    try:
        url = f"https://fundf10.eastmoney.com/ts_{fund_code}.html"
        response = _session.get(url, timeout=10)

        if response.status_code != 200:
            return {"success": False, "error": "请求失败"}

        content = response.text

        risk_level = "未知"
        risk_match = re.search(r'风险等级.*?<div[^>]*>([^<]+)</div>', content)
        if risk_match:
            risk_level = risk_match.group(1).strip()

        star_rating = 0
        star_match = re.search(r'(\d+)星', content)
        if star_match:
            star_rating = int(star_match.group(1))

        return {
            "success": True,
            "data": {
                "risk_level": risk_level,
                "star_rating": star_rating,
                "risk_description": _get_risk_description(risk_level),
            }
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def _get_risk_description(risk_level: str) -> str:
    """获取风险等级描述"""
    descriptions = {
        "低": "低风险基金，主要投资于货币市场工具，适合保守型投资者",
        "中低": "中低风险基金，波动较小，适合稳健型投资者",
        "中": "中等风险基金，收益与风险平衡，适合平衡型投资者",
        "中高": "中高风险基金，波动较大，适合积极型投资者",
        "高": "高风险基金，主要投资于股票市场，适合激进型投资者",
    }
    return descriptions.get(risk_level, "风险等级未知")


@cached(ttl=21600)
def fetch_index_data(index_code: str = "000300", days: int = 90) -> dict:
    """获取指数历史数据用于对比"""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    try:
        from akshare import index

        df = index.index_zh_a_hist(
            symbol=index_code,
            period="daily",
            start_date=start_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
        )

        if df is not None and not df.empty:
            df["日期"] = pd.to_datetime(df["日期"], errors="coerce")
            df = df.dropna(subset=["日期"]).sort_values("日期")

            base_value = _to_float(df.iloc[0]["收盘"])
            history_data = []
            for _, row in df.iterrows():
                current_value = _to_float(row["收盘"])
                if base_value <= 0 or current_value <= 0:
                    continue
                change_pct = ((current_value - base_value) / base_value) * 100
                history_data.append({
                    "date": row["日期"].strftime("%Y-%m-%d"),
                    "value": round(current_value, 2),
                    "change_pct": round(change_pct, 2),
                })

            if history_data:
                return {"success": True, "data": history_data, "index_name": _index_name(index_code)}
    except Exception as e:
        logger.warning(f"akshare index history failed for {index_code}: {e}")

    return fetch_index_data_from_eastmoney(index_code, days)


def _index_name(index_code: str) -> str:
    names = {
        "000300": "沪深300",
        "000001": "上证指数",
        "399001": "深证成指",
        "399006": "创业板指",
    }
    return names.get(index_code, index_code)


def _eastmoney_index_secid(index_code: str) -> str:
    market = "0" if index_code.startswith(("399", "159", "160")) else "1"
    return f"{market}.{index_code}"


def fetch_index_data_from_eastmoney(index_code: str = "000300", days: int = 90) -> dict:
    """Fetch index history from Eastmoney K-line endpoint as fallback."""
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
        params = {
            "secid": _eastmoney_index_secid(index_code),
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "klt": "101",
            "fqt": "1",
            "beg": start_date.strftime("%Y%m%d"),
            "end": end_date.strftime("%Y%m%d"),
        }
        response = _session.get(url, params=params, timeout=10)
        response.raise_for_status()
        payload = response.json()
        data_node = payload.get("data") or {}
        klines = data_node.get("klines") or []

        history_data = []
        base_value = 0
        for line in klines:
            parts = str(line).split(",")
            if len(parts) < 3:
                continue
            date_text = parts[0]
            close_value = _to_float(parts[2])
            if close_value <= 0:
                continue
            if base_value <= 0:
                base_value = close_value
            change_pct = _return_between(base_value, close_value)
            history_data.append({
                "date": date_text,
                "value": round(close_value, 2),
                "change_pct": round(change_pct, 2),
            })

        if not history_data:
            return {"success": False, "error": "无法获取指数数据"}

        return {
            "success": True,
            "data": history_data,
            "index_name": data_node.get("name") or _index_name(index_code),
        }
    except Exception as e:
        logger.error(f"Eastmoney index history failed for {index_code}: {e}")
        return {"success": False, "error": str(e)}


def _validate_fund_code(fund_code: str) -> tuple:
    return (True, "") if re.match(r"^\d{6}$", str(fund_code).strip()) else (False, "基金代码格式无效，请输入6位数字代码")


@fund_bp.route("/")
def index():
    """基金首页"""
    return render_template("fund/search.html")


@fund_bp.route("/search")
def search():
    """基金搜索页面"""
    return render_template("fund/search.html")


@fund_bp.route("/analysis/<fund_code>")
def analysis(fund_code: str):
    """基金分析页面"""
    valid, error = _validate_fund_code(fund_code)
    if not valid:
        return render_template("fund/analysis.html", fund_code=fund_code, error=error)
    return render_template("fund/analysis.html", fund_code=fund_code)


@fund_bp.route("/compare")
def compare():
    """基金对比页面"""
    return render_template("fund/compare.html")


@fund_bp.route("/api/realtime/<fund_code>")
def get_realtime_data(fund_code: str):
    """获取基金实时估值"""
    valid, error = _validate_fund_code(fund_code)
    if not valid:
        return jsonify({"success": False, "error": error})
    return jsonify(fetch_fund_realtime_data(fund_code))


@fund_bp.route("/api/history/<fund_code>")
def get_history_data(fund_code: str):
    """获取基金历史净值"""
    valid, error = _validate_fund_code(fund_code)
    if not valid:
        return jsonify({"success": False, "error": error})
    days = request.args.get("days", 365, type=int)
    days = min(days, 730)
    return jsonify(fetch_fund_history(fund_code, days))


@fund_bp.route("/api/holdings/<fund_code>")
def get_holdings_data(fund_code: str):
    """获取基金重仓持股"""
    valid, error = _validate_fund_code(fund_code)
    if not valid:
        return jsonify({"success": False, "error": error})
    return jsonify(fetch_fund_holdings(fund_code))


@fund_bp.route("/api/info/<fund_code>")
def get_info_data(fund_code: str):
    """获取基金详细信息"""
    valid, error = _validate_fund_code(fund_code)
    if not valid:
        return jsonify({"success": False, "error": error})
    return jsonify(fetch_fund_info(fund_code))


@fund_bp.route("/api/performance/<fund_code>")
def get_performance_data(fund_code: str):
    """获取基金业绩指标"""
    valid, error = _validate_fund_code(fund_code)
    if not valid:
        return jsonify({"success": False, "error": error})

    days = request.args.get("days", 365, type=int)
    days = min(days, 730)

    result = fetch_fund_history(fund_code, days)
    if not result["success"]:
        return jsonify(result)

    metrics = calculate_performance_metrics(result["data"])
    return jsonify({"success": True, "data": metrics})


@fund_bp.route("/api/index/<index_code>")
def get_index_data(index_code: str = "000300"):
    """获取指数数据用于对比"""
    days = request.args.get("days", 365, type=int)
    return jsonify(fetch_index_data(index_code, days))


@fund_bp.route("/api/compare")
def compare_funds():
    """对比多只基金"""
    codes = request.args.get("codes", "")
    if not codes:
        return jsonify({"success": False, "error": "请提供基金代码"})

    fund_codes = [c.strip() for c in codes.split(",") if c.strip() and re.match(r"^\d{6}$", c.strip())]

    if not fund_codes:
        return jsonify({"success": False, "error": "基金代码格式无效"})

    fund_codes = fund_codes[:5]

    results = []
    for code in fund_codes:
        realtime = fetch_fund_realtime_data(code)
        history = fetch_fund_history(code, 365)
        performance = {}
        advanced = {}

        if history["success"]:
            performance = calculate_performance_metrics(history["data"])
            benchmark = fetch_index_data("000300", 365)
            advanced = calculate_advanced_metrics(
                history["data"],
                benchmark["data"] if benchmark["success"] else None
            )
            period = calculate_period_returns(history["data"])

            # 附加各时段收益到 performance（保留 CAGR 计算的 annualized_return）
            if period:
                performance["period_returns"] = period

        results.append({
            "fund_code": code,
            "realtime": realtime.get("data", {}) if realtime["success"] else {},
            "performance": performance,
            "advanced": advanced,
        })

    return jsonify({"success": True, "data": results})


@fund_bp.route("/api/search")
def search_funds():
    """搜索基金 - 支持代码直接搜索和关键词搜索"""
    keyword = request.args.get("keyword", "").strip()
    search_type = request.args.get("type", "all")
    sort_by = request.args.get("sort", "code")
    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("page_size", 20, type=int)

    if not keyword:
        return jsonify({
            "success": True,
            "data": [],
            "total": 0,
            "page": page,
            "page_size": page_size,
            "total_pages": 0,
            "source": "empty_keyword"
        })

    # 如果输入的是6位数字基金代码，直接验证
    if re.match(r"^\d{6}$", keyword):
        result = verify_fund_by_realtime_api(keyword)
        if result["success"]:
            return jsonify({
                "success": True,
                "data": [result["data"]],
                "total": 1,
                "page": 1,
                "page_size": 1,
                "total_pages": 1,
                "source": "realtime_api"
            })
        else:
            return jsonify({
                "success": True,
                "data": [],
                "total": 0,
                "page": 1,
                "page_size": 0,
                "total_pages": 0,
                "source": "not_found"
            })

    # 否则用关键词搜索，先尝试API
    api_results = search_funds_from_api(keyword, search_type)

    if api_results:
        results = api_results
    else:
        # 使用全局的_FALLBACK_FUNDS元组
        kw = keyword.lower()
        results = [_fmt_fund(f) for f in _FALLBACK_FUNDS
                   if kw in f[1].lower() or kw in f[0] or kw in f[4].lower() or kw in f[2].lower()]

    type_map = {"stock":"股票型","mix":"混合型","index":"指数型","bond":"债券型","money":"货币型","qdii":"QDII"}
    if search_type != "all":
        mapped_type = type_map.get(search_type, search_type)
        results = [f for f in results if f["fund_type"] == mapped_type]

    if sort_by == "code":
        results.sort(key=lambda x: x["fund_code"])
    elif sort_by == "name":
        results.sort(key=lambda x: x["fund_name"])

    total = len(results)
    start = (page - 1) * page_size
    end = start + page_size
    paginated = results[start:end]

    source = "api" if api_results else "fallback"

    return jsonify({
        "success": True,
        "data": paginated,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if page_size > 0 else 0,
        "source": source
    })


@fund_bp.route("/ranking")
def ranking():
    """基金排行榜页面"""
    return render_template("fund/ranking.html")


@fund_bp.route("/api/ranking")
def get_ranking():
    """获取基金排行榜"""
    rank_type = request.args.get("type", "stock")
    period = request.args.get("period", "1y")
    theme = request.args.get("theme", "all")
    sort_period = period
    result = _RANKINGS.get(rank_type, _RANKINGS.get("stock", ()))
    return jsonify({"success": True, "data": [_fmt_ranking(r) for r in result], "type": rank_type, "period": sort_period, "theme": theme})


@fund_bp.route("/api/advanced-metrics/<fund_code>")
def get_advanced_metrics(fund_code: str):
    """获取基金高级业绩指标"""
    valid, error = _validate_fund_code(fund_code)
    if not valid:
        return jsonify({"success": False, "error": error})

    days = request.args.get("days", 365, type=int)
    days = min(days, 730)
    index_code = request.args.get("index", "000300")

    history_result = fetch_fund_history(fund_code, days)
    if not history_result["success"]:
        return jsonify(history_result)

    benchmark_result = fetch_index_data(index_code, days) if index_code else None

    metrics = calculate_advanced_metrics(
        history_result["data"],
        benchmark_result["data"] if benchmark_result and benchmark_result["success"] else None
    )

    return jsonify({"success": True, "data": metrics})


@fund_bp.route("/api/period-returns/<fund_code>")
def get_period_returns(fund_code: str):
    """获取基金多时段收益"""
    valid, error = _validate_fund_code(fund_code)
    if not valid:
        return jsonify({"success": False, "error": error})

    history_result = fetch_fund_history(fund_code, 1825)
    if not history_result["success"]:
        return jsonify(history_result)

    period_returns = calculate_period_returns(history_result["data"])
    return jsonify({"success": True, "data": period_returns})


@fund_bp.route("/api/fixed-investment/<fund_code>")
def get_fixed_investment(fund_code: str):
    """定投收益模拟"""
    valid, error = _validate_fund_code(fund_code)
    if not valid:
        return jsonify({"success": False, "error": error})

    monthly_amount = request.args.get("amount", 1000, type=float)
    monthly_amount = max(100, min(monthly_amount, 100000))

    history_result = fetch_fund_history(fund_code, 1825)
    if not history_result["success"]:
        return jsonify(history_result)

    result = simulate_fixed_investment(history_result["data"], monthly_amount)
    return jsonify(result)


@fund_bp.route("/api/correlation/<fund_code>")
def get_correlation(fund_code: str):
    """相关性分析"""
    valid, error = _validate_fund_code(fund_code)
    if not valid:
        return jsonify({"success": False, "error": error})

    index_code = request.args.get("index", "000300")
    history_result = fetch_fund_history(fund_code, 365)
    if not history_result["success"]:
        return jsonify(history_result)

    result = calculate_correlation_with_index(history_result["data"], index_code)
    return jsonify(result)


@fund_bp.route("/api/allocation/<fund_code>")
def get_allocation(fund_code: str):
    """获取基金资产配置"""
    valid, error = _validate_fund_code(fund_code)
    if not valid:
        return jsonify({"success": False, "error": error})

    return jsonify(fetch_fund_asset_allocation(fund_code))


@fund_bp.route("/api/manager/<fund_code>")
def get_manager(fund_code: str):
    """获取基金经理信息"""
    valid, error = _validate_fund_code(fund_code)
    if not valid:
        return jsonify({"success": False, "error": error})

    return jsonify(fetch_fund_manager_info(fund_code))


@fund_bp.route("/api/dividend/<fund_code>")
def get_dividend(fund_code: str):
    """获取基金分红历史"""
    valid, error = _validate_fund_code(fund_code)
    if not valid:
        return jsonify({"success": False, "error": error})

    return jsonify(fetch_fund_dividend_history(fund_code))


@fund_bp.route("/api/risk/<fund_code>")
def get_risk(fund_code: str):
    """获取基金风险评级"""
    valid, error = _validate_fund_code(fund_code)
    if not valid:
        return jsonify({"success": False, "error": error})

    return jsonify(fetch_fund_risk_metrics(fund_code))


@fund_bp.route("/api/full-analysis/<fund_code>")
def get_full_analysis(fund_code: str):
    """获取完整基金分析报告"""
    valid, error = _validate_fund_code(fund_code)
    if not valid:
        return jsonify({"success": False, "error": error})

    try:
        days = 365

        realtime = fetch_fund_realtime_data(fund_code)
        history = fetch_fund_history(fund_code, days)
        info = fetch_fund_info(fund_code)
        holdings = fetch_fund_holdings(fund_code)

        basic_metrics = {}
        advanced_metrics = {}
        period_returns = {}
        correlation = {}

        if history["success"]:
            basic_metrics = calculate_performance_metrics(history["data"])
            benchmark = fetch_index_data("000300", days)
            advanced_metrics = calculate_advanced_metrics(
                history["data"],
                benchmark["data"] if benchmark["success"] else None
            )
            period_returns = calculate_period_returns(history["data"])
            correlation = calculate_correlation_with_index(history["data"], "000300")

        allocation = fetch_fund_asset_allocation(fund_code)
        risk = fetch_fund_risk_metrics(fund_code)

        return jsonify({
            "success": True,
            "data": {
                "realtime": realtime.get("data", {}) if realtime["success"] else {},
                "info": info.get("data", {}) if info["success"] else {},
                "basic_metrics": basic_metrics,
                "advanced_metrics": advanced_metrics,
                "period_returns": period_returns,
                "correlation": correlation.get("data", {}) if correlation["success"] else {},
                "allocation": allocation.get("data", []) if allocation["success"] else [],
                "risk": risk.get("data", {}) if risk["success"] else {},
                "holdings": holdings.get("data", []) if holdings["success"] else [],
            }
        })
    except Exception as e:
        logger.error(f"Full analysis error: {e}")
        return jsonify({"success": False, "error": str(e)})
