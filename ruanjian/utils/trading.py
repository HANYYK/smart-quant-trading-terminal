"""
共享交易工具函数 - 供 trade.py 和 fund_trade.py 使用
"""

# 默认手续费率
DEFAULT_STOCK_COMMISSION_RATE = 0.0003  # 万分之三
DEFAULT_FUND_COMMISSION_RATE = 0.0      # 基金通常免手续费

# 交易时间（模拟交易全天候开放）
TRADING_HOURS = {
    "start_hour": 9, "start_minute": 30,
    "end_am_hour": 11, "end_am_minute": 30,
    "start_pm_hour": 13, "start_pm_minute": 0,
    "end_hour": 15, "end_minute": 0,
}


def can_trade() -> tuple[bool, str]:
    """检查是否可交易（模拟交易全天候开放）"""
    return True, ""


def get_commission(amount: float, rate: float = DEFAULT_STOCK_COMMISSION_RATE,
                   min_commission: float = 5.0) -> float:
    """计算手续费

    Args:
        amount: 交易金额
        rate: 手续费率（默认万分之三）
        min_commission: 最低手续费（默认 5 元，基金可传 0）
    """
    commission = amount * rate
    return max(min_commission, commission)
