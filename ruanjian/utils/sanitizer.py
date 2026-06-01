"""
安全工具模块 - 输入验证和sanitization
"""
import re
import html
from typing import Optional, Tuple


def sanitize_string(value: str, max_length: int = 255) -> str:
    """清理字符串，移除潜在的危险字符"""
    if not value:
        return ""
    # HTML转义
    value = html.escape(value)
    # 移除控制字符
    value = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", value)
    return value[:max_length]


def validate_stock_code(code: str) -> Tuple[bool, Optional[str]]:
    """验证股票代码格式"""
    if not code:
        return False, "股票代码不能为空"

    code = code.strip().lower()

    # 支持的格式: sh.600000, sz.000000, bj.000000
    pattern = r"^(sh|sz|bj)\.\d{6}$"
    if re.match(pattern, code):
        return True, None

    return False, "股票代码格式无效，应为 sh.600000、sz.000000 或 bj.000000"


def validate_fund_code(code: str) -> Tuple[bool, Optional[str]]:
    """验证基金代码格式"""
    if not code:
        return False, "基金代码不能为空"

    code = code.strip()

    if not re.match(r"^\d{6}$", code):
        return False, "基金代码格式无效，应为6位数字"

    return True, None


def validate_date_format(date_str: str) -> Tuple[bool, Optional[str]]:
    """验证日期格式"""
    if not date_str:
        return False, "日期不能为空"

    pattern = r"^\d{4}-\d{2}-\d{2}$"
    if not re.match(pattern, date_str):
        return False, "日期格式无效，应为 YYYY-MM-DD"

    try:
        from datetime import datetime
        datetime.strptime(date_str, "%Y-%m-%d")
        return True, None
    except ValueError:
        return False, "日期无效"


def validate_page_params(page: int, page_size: int,
                         max_page_size: int = 100) -> Tuple[bool, Optional[str], int, int]:
    """验证分页参数"""
    if page < 1:
        return False, "页码必须大于0", 1, page_size

    if page_size < 1:
        return False, "每页数量必须大于0", page, 20

    if page_size > max_page_size:
        return False, f"每页数量不能超过 {max_page_size}", page, max_page_size

    return True, None, page, page_size


def validate_search_keyword(keyword: str, max_length: int = 100) -> Tuple[bool, Optional[str], str]:
    """验证搜索关键词"""
    if not keyword:
        return True, None, ""

    keyword = keyword.strip()

    if len(keyword) > max_length:
        return False, f"关键词不能超过 {max_length} 个字符", keyword[:max_length]

    # 移除可能的SQL注入尝试
    dangerous_patterns = [
        r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|UNION)\b)",
        r"(--|#|/\*|\*/)",
        r"(\bOR\b.*=.*\bOR\b)",
    ]

    for pattern in dangerous_patterns:
        if re.search(pattern, keyword, re.IGNORECASE):
            return False, "搜索关键词包含无效字符", sanitize_string(keyword, 50)

    return True, None, keyword


def validate_number_range(value: float, min_val: float, max_val: float,
                          param_name: str = "值") -> Tuple[bool, Optional[str]]:
    """验证数字范围"""
    if value < min_val:
        return False, f"{param_name}不能小于 {min_val}"

    if value > max_val:
        return False, f"{param_name}不能大于 {max_val}"

    return True, None


def validate_url_safe(value: str) -> Tuple[bool, Optional[str]]:
    """验证URL安全参数"""
    if not value:
        return True, None

    # 禁止javascript:协议
    if re.search(r"javascript\s*:", value, re.IGNORECASE):
        return False, "禁止使用JavaScript协议"

    # 禁止data:协议（可用于XSS）
    if re.search(r"data\s*:", value, re.IGNORECASE):
        return False, "禁止使用data协议"

    return True, None


def strip_whitespace(value: str) -> str:
    """去除首尾空白字符"""
    return value.strip() if value else ""
