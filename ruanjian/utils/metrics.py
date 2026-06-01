"""
共享指标计算工具模块
消除重复代码，提供统一的指标计算函数
"""
import numpy as np
from typing import List, Dict, Any


def max_drawdown(values: List[float]) -> float:
    """计算最大回撤（百分比）"""
    if not values or len(values) < 2:
        return 0.0
    peak = values[0]
    max_dd = 0.0
    for value in values:
        peak = max(peak, value)
        if peak > 0:
            dd = (value - peak) / peak
            max_dd = min(max_dd, dd)
    return max_dd * 100


def calculate_sharpe_ratio(returns: List[float], risk_free_rate: float = 0.03) -> float:
    """计算年化夏普比率"""
    if not returns or len(returns) < 2:
        return 0.0
    returns_array = np.array(returns)
    excess_returns = returns_array - risk_free_rate / 252
    std = np.std(excess_returns)
    if std == 0:
        return 0.0
    return float(np.mean(excess_returns) / std * np.sqrt(252))


def calculate_win_loss_ratio(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    """计算胜负比"""
    sell_trades = [
        t for t in trades
        if t.get("action") == "sell" and t.get("profit_pct") is not None
    ]
    if not sell_trades:
        return {"win_count": 0, "loss_count": 0, "ratio": 0, "avg_win": 0, "avg_loss": 0}

    wins = [t for t in sell_trades if t["profit_pct"] > 0]
    losses = [t for t in sell_trades if t["profit_pct"] <= 0]

    avg_win = np.mean([t["profit_pct"] for t in wins]) if wins else 0
    avg_loss = abs(np.mean([t["profit_pct"] for t in losses])) if losses else 0

    return {
        "win_count": len(wins),
        "loss_count": len(losses),
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "ratio": avg_win / avg_loss if avg_loss > 0 else 0
    }


def calculate_sortino_ratio(returns: List[float], risk_free_rate: float = 0.03) -> float:
    """计算索提诺比率"""
    if not returns or len(returns) < 2:
        return 0.0

    returns_array = np.array(returns)
    downside_returns = returns_array[returns_array < 0]
    downside_std = np.std(downside_returns) if len(downside_returns) > 1 else 0

    if downside_std == 0:
        return 0.0

    mean_return = np.mean(returns_array) * 252
    return float(mean_return / (downside_std * np.sqrt(252)))


def calculate_volatility(returns: List[float]) -> float:
    """计算年化波动率"""
    if not returns or len(returns) < 2:
        return 0.0
    return float(np.std(returns) * np.sqrt(252) * 100)


def calculate_calmar_ratio(total_return: float, max_drawdown_val: float) -> float:
    """计算卡玛比率（年化收益 / 最大回撤）"""
    if max_drawdown_val == 0:
        return 0.0
    return total_return / max_drawdown_val


def calculate_win_rate(trades: List[Dict[str, Any]]) -> float:
    """计算胜率"""
    sell_trades = [
        t for t in trades
        if t.get("action") == "sell" and t.get("profit_pct") is not None
    ]
    if not sell_trades:
        return 0.0
    wins = sum(1 for t in sell_trades if t["profit_pct"] > 0)
    return wins / len(sell_trades) * 100


def calculate_profit_factor(trades: List[Dict[str, Any]]) -> float:
    """计算盈利因子（总盈利 / 总亏损）"""
    sell_trades = [
        t for t in trades
        if t.get("action") == "sell" and t.get("profit_pct") is not None
    ]
    if not sell_trades:
        return 0.0

    wins = [t["profit_pct"] for t in sell_trades if t["profit_pct"] > 0]
    losses = [abs(t["profit_pct"]) for t in sell_trades if t["profit_pct"] < 0]

    total_profit = sum(wins) if wins else 0
    total_loss = sum(losses) if losses else 0

    if total_loss == 0:
        return total_profit if total_profit > 0 else 0
    return total_profit / total_loss
