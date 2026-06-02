"""
基金工具函数 - 供 fund.py 和 fund_trade.py 共享
"""
import re
import json
import logging
from datetime import datetime

import pandas as pd
import requests

logger = logging.getLogger(__name__)

# ==================== 常量 ====================
FUND_API_BASE = "http://fundgz.1234567.com.cn/js"

INVALID_FUND_NAME_KEYWORDS = (
    "郑重声明",
    "天天基金网发布",
    "与本网站立场无关",
    "不保证该信息",
    "投资决策建议",
    "风险自担",
    "数据来源",
    "东方财富Choice数据",
)

# ==================== HTTP Session ====================
_session = requests.Session()
_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "http://fund.eastmoney.com/",
})


def get_session() -> requests.Session:
    """获取共享 HTTP Session"""
    return _session


# ==================== 基金代码/名称 ====================
def normalize_fund_code(fund_code: str) -> str:
    """从任意输入提取 6 位数字基金代码"""
    return re.sub(r"\D", "", str(fund_code or ""))[:6]


def validate_fund_code(fund_code: str) -> tuple:
    """验证基金代码格式 → (bool, error_msg)"""
    if re.match(r"^\d{6}$", str(fund_code).strip()):
        return True, ""
    return False, "基金代码格式无效，请输入6位数字代码"


def guess_type(name: str) -> str:
    """根据基金名称推断类型"""
    if any(k in name for k in ["指数", "ETF", "联接"]):
        return "指数型"
    if "货币" in name:
        return "货币型"
    if any(k in name for k in ["债券", "纯债", "信用债"]):
        return "债券型"
    if any(k in name for k in ["QDII", "海外", "纳斯达克"]):
        return "QDII"
    if "股票" in name:
        return "股票型"
    return "混合型"


def clean_html_text(value: str) -> str:
    """清洗从基金页面抓取的 HTML 文本"""
    if not value:
        return ""
    value = re.sub(r"<[^>]+>", "", str(value))
    value = re.sub(r"\s+", " ", value)
    return value.strip(" \t\r\n:：")


def is_valid_fund_name(name: str, fund_code: str = "") -> bool:
    """拒绝抓取到的免责声明等无效名称"""
    name = clean_html_text(name)
    if not name:
        return False
    if fund_code and name == fund_code:
        return False
    if len(name) > 80:
        return False
    if any(keyword in name for keyword in INVALID_FUND_NAME_KEYWORDS):
        return False
    return True


# ==================== 数据解析 ====================
def parse_jsonp(content: str) -> dict | None:
    """解析 JSONP 响应"""
    match = re.search(r"jsonpgz\(\{(.+?)\}\)", content, re.DOTALL)
    if not match:
        return None
    try:
        raw = "{" + match.group(1) + "}"
        raw = raw.replace("None", "null").replace("True", "true").replace("False", "false")
        return json.loads(raw)
    except Exception:
        return None


def to_float(value, default: float = 0) -> float:
    """安全转换为 float"""
    try:
        if value is None or pd.isna(value):
            return default
        value_text = str(value).strip().replace(",", "").replace("%", "")
        if value_text in ("", "--", "-"):
            return default
        return float(value_text)
    except Exception:
        return default


def parse_history_date(value) -> datetime | None:
    """解析基金/指数数据中的日期字符串"""
    if value is None:
        return None
    if hasattr(value, "to_pydatetime"):
        return value.to_pydatetime()
    if hasattr(value, "strftime") and not isinstance(value, str):
        return value
    try:
        if isinstance(value, str) and value.isdigit() and len(value) == 8:
            return datetime.strptime(value, "%Y%m%d")
    except Exception:
        pass
    return None


def sorted_history(history_data: list) -> list:
    """按日期升序排列历史数据 — 纯函数，直接返回新列表"""
    return sorted(history_data, key=lambda x: str(x.get("date", "")))
