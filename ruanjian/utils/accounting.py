"""
Shared account snapshot helpers for simulated stock and fund trading.
"""
from __future__ import annotations

from typing import Any

from models import FundPosition, FundTrade, Portfolio, Trade


def _round_money(value: float) -> float:
    return round(float(value or 0), 2)


def _round_nav(value: float) -> float:
    return round(float(value or 0), 4)


def build_stock_positions(user_id: int) -> tuple[float, list[dict[str, Any]]]:
    """Return stock position value and rows using cost price for fast overview."""
    positions = (
        Portfolio.query
        .filter_by(user_id=user_id)
        .filter(Portfolio.quantity > 0)
        .all()
    )

    position_value = 0.0
    rows: list[dict[str, Any]] = []

    for position in positions:
        market_value = float(position.quantity or 0) * float(position.avg_cost or 0)
        position_value += market_value
        rows.append({
            "stock_code": position.stock_code,
            "stock_name": position.stock_name,
            "quantity": position.quantity,
            "avg_cost": _round_money(position.avg_cost),
            "current_price": _round_money(position.avg_cost),
            "market_value": _round_money(market_value),
            "profit": 0.0,
            "profit_rate": 0.0,
        })

    return position_value, rows


def build_fund_positions(user_id: int) -> tuple[float, list[dict[str, Any]]]:
    """Return fund position value and rows using cost NAV for fast overview."""
    positions = (
        FundPosition.query
        .filter_by(user_id=user_id)
        .filter(FundPosition.total_shares > 0)
        .all()
    )

    position_value = 0.0
    rows: list[dict[str, Any]] = []

    for position in positions:
        current_nav = float(position.avg_cost or 0)
        market_value = float(position.total_shares or 0) * current_nav
        position_value += market_value
        rows.append({
            "fund_code": position.fund_code,
            "fund_name": position.fund_name,
            "total_shares": round(float(position.total_shares or 0), 2),
            "avg_cost": _round_nav(position.avg_cost),
            "current_nav": _round_nav(current_nav),
            "market_value": _round_money(market_value),
            "profit": 0.0,
            "profit_rate": 0.0,
        })

    return position_value, rows


def build_account_snapshot(user: Any) -> dict[str, Any]:
    """
    Build one consistent cross-asset account snapshot.

    Cash is shared by stock and fund trading, so total assets must include both
    stock positions and fund positions. Otherwise buying a fund looks like a
    loss in the stock account overview because cash went down but fund value was
    not added back.
    """
    stock_value, stock_positions = build_stock_positions(user.id)
    fund_value, fund_positions = build_fund_positions(user.id)
    total_position_value = stock_value + fund_value
    stock_profit = sum(float(row["profit"] or 0) for row in stock_positions)
    fund_profit = sum(float(row["profit"] or 0) for row in fund_positions)
    total_position_profit = stock_profit + fund_profit
    total_assets = float(user.current_cash or 0) + total_position_value
    stock_realized_profit = (
        Trade.query
        .filter_by(user_id=user.id, action=Trade.ACTION_SELL)
        .filter(Trade.profit.isnot(None))
        .with_entities(Trade.profit)
        .all()
    )
    fund_realized_profit = (
        FundTrade.query
        .filter_by(user_id=user.id, action=FundTrade.ACTION_SELL)
        .filter(FundTrade.profit.isnot(None))
        .with_entities(FundTrade.profit)
        .all()
    )
    realized_profit = (
        sum(float(row[0] or 0) for row in stock_realized_profit)
        + sum(float(row[0] or 0) for row in fund_realized_profit)
    )
    total_profit = realized_profit + total_position_profit
    profit_rate = (
        total_profit / float(user.initial_cash) * 100
        if float(user.initial_cash or 0) > 0
        else 0.0
    )

    return {
        "initial_cash": _round_money(user.initial_cash),
        "current_cash": _round_money(user.current_cash),
        "cash": _round_money(user.current_cash),
        "frozen_cash": _round_money(user.frozen_cash),
        "stock_position_value": _round_money(stock_value),
        "fund_position_value": _round_money(fund_value),
        "total_position_value": _round_money(total_position_value),
        "stock_position_profit": _round_money(stock_profit),
        "fund_position_profit": _round_money(fund_profit),
        "total_position_profit": _round_money(total_position_profit),
        "realized_profit": _round_money(realized_profit),
        "total_assets": _round_money(total_assets),
        "total_profit": _round_money(total_profit),
        "profit_rate": round(profit_rate, 2),
        "stock_position_count": len(stock_positions),
        "fund_position_count": len(fund_positions),
        "stock_positions": stock_positions,
        "fund_positions": fund_positions,
    }
