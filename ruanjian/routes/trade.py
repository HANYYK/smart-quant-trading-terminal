"""
模拟交易路由 - 买入、卖出、持仓管理、交易记录
"""
from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user
from datetime import datetime, timezone
from sqlalchemy import desc, func, case
import logging
import re

from extensions import db
from models import FixedInvestment, FundPosition, FundTrade, Portfolio, Trade, TradingSummary
from utils.accounting import build_account_snapshot

logger = logging.getLogger(__name__)
trade_bp = Blueprint("trade", __name__, url_prefix="/trade")

# 默认手续费率
DEFAULT_COMMISSION_RATE = 0.0003  # 万三

# 交易时间限制（模拟交易全天候开放）
# 周六日使用最近一个交易日（周五）的收盘价
TRADING_HOURS = {
    "start_hour": 9, "start_minute": 30,
    "end_am_hour": 11, "end_am_minute": 30,
    "start_pm_hour": 13, "start_pm_minute": 0,
    "end_hour": 15, "end_minute": 0
}

from utils.trading import can_trade, get_commission


def is_supported_stock_code(stock_code: str) -> bool:
    """Check common A-share stock code ranges to keep fund codes out of stock trading."""
    code = (stock_code or "").strip().lower()
    if not re.match(r"^(sh|sz|bj)\.\d{6}$", code):
        return False

    market, digits = code.split(".", 1)
    if market == "sh":
        return digits.startswith(("600", "601", "603", "605", "688", "689", "900"))
    if market == "sz":
        return digits.startswith(("000", "001", "002", "003", "300", "301", "200"))
    if market == "bj":
        return digits.startswith(("43", "83", "87", "88", "92"))
    return False


def get_stock_price_from_api(stock_code: str) -> tuple[float, str]:
    """从API获取股票当前价格（带超时控制）"""
    try:
        import threading
        import time as time_module

        result = {"price": 0.0, "date": ""}
        error = {"err": None}

        def fetch_price():
            try:
                from routes.stock import fetch_kline_data
                df = fetch_kline_data(stock_code, count=5)
                if not df.empty:
                    for i in range(len(df) - 1, -1, -1):
                        close_price = df.iloc[i]["close"]
                        if close_price and float(close_price) > 0:
                            result["price"] = float(close_price)
                            result["date"] = df.iloc[i].get("date", "")
                            return
            except Exception as e:
                error["err"] = e

        # 使用线程实现超时
        thread = threading.Thread(target=fetch_price)
        thread.daemon = True
        thread.start()
        thread.join(timeout=3)  # 3秒超时

        return result["price"], result["date"]
    except Exception as e:
        logger.warning(f"获取股票价格失败 {stock_code}: {e}")
        return 0.0, ""


def get_stock_info(stock_code: str) -> dict:
    """获取股票信息（周六日使用周五收盘价）"""
    try:
        from routes.stock import fetch_kline_data
        now = datetime.now()

        # 如果是周末，使用最近一个交易日的数据
        if now.weekday() >= 5:
            # 获取最近30天数据来找到周五
            df = fetch_kline_data(stock_code, count=30)
            if not df.empty:
                # 查找最近的周五数据
                friday_close = None
                friday_prev_close = None
                for i in range(len(df) - 1, -1, -1):
                    date_str = df.iloc[i].get("date", "")
                    if date_str:
                        try:
                            date = datetime.strptime(date_str, "%Y-%m-%d")
                            if date.weekday() == 4:  # 周五
                                friday_close = float(df.iloc[i]["close"])
                                # 获取周五的前一天（周四）收盘价作为前收盘
                                if i + 1 < len(df):
                                    friday_prev_close = float(df.iloc[i + 1]["close"])
                                else:
                                    friday_prev_close = friday_close
                                break
                        except ValueError:
                            continue

                if friday_close is not None:
                    close = friday_close
                    prev_close = friday_prev_close if friday_prev_close else close
                    pct_chg = (close - prev_close) / prev_close * 100 if prev_close > 0 else 0
                    return {
                        "code": stock_code,
                        "name": _get_stock_name(stock_code),
                        "price": close,
                        "prev_close": prev_close,
                        "change": close - prev_close,
                        "change_pct": pct_chg,
                        "is_friday_price": True,  # 标记是否使用周五价格
                    }
        else:
            # 工作日直接获取最新数据
            df = fetch_kline_data(stock_code, count=1)
            if not df.empty:
                prev_close = float(df.iloc[-2]["close"]) if len(df) > 1 else float(df.iloc[-1]["close"])
                close = float(df.iloc[-1]["close"])
                pct_chg = (close - prev_close) / prev_close * 100 if prev_close > 0 else 0
                return {
                    "code": stock_code,
                    "name": _get_stock_name(stock_code),
                    "price": close,
                    "prev_close": prev_close,
                    "change": close - prev_close,
                    "change_pct": pct_chg,
                }
    except Exception:
        pass
    return {"code": stock_code, "name": _get_stock_name(stock_code), "price": 0, "prev_close": 0, "change": 0, "change_pct": 0}


def _get_stock_name(code: str) -> str:
    """获取股票名称（简单映射）"""
    name_map = {
        "sh.600519": "贵州茅台", "sh.600036": "招商银行", "sz.000858": "五粮液",
        "sz.000333": "美的集团", "sh.601318": "中国平安", "sz.002594": "比亚迪",
        "sh.600276": "恒瑞医药", "sz.300750": "宁德时代", "sh.600887": "伊利股份",
        "sz.002415": "海康威视", "sh.601012": "隆基绿能", "sz.000001": "平安银行",
        "sh.600030": "中信证券", "sz.002475": "立讯精密", "sh.601888": "中国中免",
        "sz.300059": "东方财富", "sh.600900": "长江电力", "sz.002714": "牧原股份",
    }
    return name_map.get(code, code.split(".")[-1] if "." in code else code)


@trade_bp.route("/")
@login_required
def index():
    """交易主页"""
    return render_template("trade/index.html")


@trade_bp.route("/position")
@login_required
def position():
    """持仓页面"""
    return render_template("trade/position.html")


@trade_bp.route("/orders")
@login_required
def orders():
    """交易记录页面"""
    return render_template("trade/orders.html")


@trade_bp.route("/account")
@login_required
def account():
    """账户页面"""
    return render_template("trade/account.html")


@trade_bp.route("/api/account/info")
@login_required
def get_account_info():
    """获取账户信息"""
    try:
        snapshot = build_account_snapshot(current_user)

        return jsonify({
            "success": True,
            "data": {
                **snapshot,
                "position_value": snapshot["stock_position_value"],
                "position_count": snapshot["stock_position_count"],
                "positions": snapshot["stock_positions"],
            }
        })
    except Exception as e:
        logger.exception("获取账户信息失败")
        return jsonify({"success": False, "error": str(e)}), 500


@trade_bp.route("/api/position/list")
@login_required
def get_position_list():
    """获取持仓列表"""
    try:
        positions = Portfolio.query.filter_by(user_id=current_user.id).filter(Portfolio.quantity > 0).all()
        result = []
        for p in positions:
            price, _ = get_stock_price_from_api(p.stock_code)
            market_value = p.quantity * price
            profit = (price - p.avg_cost) * p.quantity
            profit_rate = (price - p.avg_cost) / p.avg_cost * 100 if p.avg_cost > 0 else 0
            result.append({
                "id": p.id,
                "stock_code": p.stock_code,
                "stock_name": p.stock_name,
                "quantity": p.quantity,
                "avg_cost": round(p.avg_cost, 2),
                "current_price": round(price, 2),
                "market_value": round(market_value, 2),
                "profit": round(profit, 2),
                "profit_rate": round(profit_rate, 2),
                "can_sell": True,
            })
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@trade_bp.route("/api/trade/list")
@login_required
def get_trade_list():
    """获取交易记录"""
    try:
        page = request.args.get("page", 1, type=int)
        page_size = request.args.get("page_size", 20, type=int)
        stock_code = request.args.get("stock_code", "")

        query = Trade.query.filter_by(user_id=current_user.id)
        if stock_code:
            query = query.filter_by(stock_code=stock_code)

        query = query.order_by(desc(Trade.created_at))
        pagination = query.paginate(page=page, per_page=page_size, error_out=False)

        trades = []
        for t in pagination.items:
            trades.append({
                "id": t.id,
                "stock_code": t.stock_code,
                "stock_name": t.stock_name,
                "action": t.action,
                "quantity": t.quantity,
                "price": round(t.price, 2),
                "commission": round(t.commission, 2),
                "total_amount": round(t.total_amount, 2),
                "profit_pct": round(t.profit, 2) if t.profit is not None else None,
                "created_at": t.created_at.strftime("%Y-%m-%d %H:%M"),
            })

        return jsonify({
            "success": True,
            "data": trades,
            "total": pagination.total,
            "pages": pagination.pages,
            "page": page,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@trade_bp.route("/api/stock/quote/<stock_code>")
@login_required
def get_stock_quote(stock_code: str):
    """获取股票行情"""
    try:
        if not is_supported_stock_code(stock_code):
            return jsonify({
                "success": False,
                "error": "股票代码格式或代码段无效；基金请到基金交易页面操作"
            })

        info = get_stock_info(stock_code)

        # 检查是否持有
        position = Portfolio.query.filter_by(user_id=current_user.id, stock_code=stock_code).first()
        holding = None
        if position and position.quantity > 0:
            holding = {
                "quantity": position.quantity,
                "avg_cost": round(position.avg_cost, 2),
                "market_value": round(position.quantity * info["price"], 2),
                "profit": round((info["price"] - position.avg_cost) * position.quantity, 2),
                "profit_rate": round((info["price"] - position.avg_cost) / position.avg_cost * 100, 2) if position.avg_cost > 0 else 0,
            }

        return jsonify({
            "success": True,
            "data": {
                "stock": info,
                "holding": holding,
                "can_trade": can_trade()[0],
                "trade_message": can_trade()[1],
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@trade_bp.route("/api/buy", methods=["POST"])
@login_required
def buy_stock():
    """买入股票"""
    try:
        can_trade_now, msg = can_trade()
        if not can_trade_now:
            return jsonify({"success": False, "error": msg}), 400

        data = request.get_json()
        stock_code = (data.get("stock_code") or "").strip()
        quantity = data.get("quantity") or 0
        price = data.get("price") or 0
        if isinstance(quantity, str):
            try:
                quantity = int(quantity)
            except ValueError:
                return jsonify({"success": False, "error": "数量格式错误，请输入整数"}), 400
        if isinstance(price, str):
            try:
                price = float(price)
            except ValueError:
                return jsonify({"success": False, "error": "价格格式错误，请输入数字"}), 400

        if not stock_code:
            return jsonify({"success": False, "error": "股票代码不能为空"}), 400
        if not is_supported_stock_code(stock_code):
            return jsonify({"success": False, "error": "股票代码格式或代码段无效；基金请到基金交易页面操作"}), 400
        if not isinstance(quantity, int) or quantity <= 0:
            return jsonify({"success": False, "error": "买入数量必须大于0"}), 400
        if quantity % 100 != 0:
            return jsonify({"success": False, "error": "买入数量必须为100的整数倍"}), 400
        if not isinstance(price, (int, float)) or price <= 0:
            return jsonify({"success": False, "error": "价格必须大于0"}), 400
        if price > 10000:
            return jsonify({"success": False, "error": "价格异常（超过10000元），请核实后重试"}), 400

        # 获取股票信息（失败时使用备用方案）
        stock_info = get_stock_info(stock_code)
        stock_name = stock_info.get("name") or _get_stock_name(stock_code) or stock_code
        stock_price = stock_info.get("price", 0)
        if stock_price <= 0:
            stock_price = price  # 使用用户输入的价格作为备用

        # 计算金额
        total_amount = quantity * price
        commission = get_commission(total_amount)
        total_cost = total_amount + commission

        # 检查资金
        user = current_user
        if user.current_cash < total_cost:
            return jsonify({
                "success": False,
                "error": f"资金不足。需要 {total_cost:.2f}元，当前可用 {user.current_cash:.2f}元"
            }), 400

        # 更新持仓
        portfolio = Portfolio.query.filter_by(user_id=user.id, stock_code=stock_code).first()
        if portfolio:
            total_shares = portfolio.quantity + quantity
            total_invested = portfolio.quantity * portfolio.avg_cost + total_amount
            portfolio.avg_cost = total_invested / total_shares
            portfolio.quantity = total_shares
            portfolio.updated_at = datetime.now(timezone.utc)
        else:
            portfolio = Portfolio(
                user_id=user.id,
                stock_code=stock_code,
                stock_name=stock_name,
                quantity=quantity,
                avg_cost=total_amount / quantity,  # 使用实际成交金额计算平均成本
            )
            db.session.add(portfolio)

        # 扣除资金
        user.current_cash -= total_cost

        # 记录交易
        trade = Trade(
            user_id=user.id,
            stock_code=stock_code,
            stock_name=stock_name,
            action=Trade.ACTION_BUY,
            quantity=quantity,
            price=price,
            commission=commission,
            total_amount=total_amount,
        )
        db.session.add(trade)
        db.session.commit()

        logger.info(f"用户 {user.id} 买入 {stock_code} x {quantity} @ {price}")

        return jsonify({
            "success": True,
            "message": f"买入成功！\n股票: {stock_name}\n数量: {quantity}股\n价格: {price:.2f}元\n手续费: {commission:.2f}元\n总金额: {total_cost:.2f}元",
            "data": {
                "trade_id": trade.id,
                "stock_code": stock_code,
                "stock_name": stock_name,
                "quantity": quantity,
                "price": price,
                "commission": commission,
                "total_cost": total_cost,
                "remaining_cash": round(user.current_cash, 2),
            }
        })

    except Exception as e:
        db.session.rollback()
        logger.exception("买入失败")
        return jsonify({"success": False, "error": f"买入失败: {str(e)}"}), 500


@trade_bp.route("/api/sell", methods=["POST"])
@login_required
def sell_stock():
    """卖出股票"""
    try:
        can_trade_now, msg = can_trade()
        if not can_trade_now:
            return jsonify({"success": False, "error": msg}), 400

        data = request.get_json()
        stock_code = (data.get("stock_code") or "").strip()
        quantity = data.get("quantity") or 0
        price = data.get("price") or 0
        if isinstance(quantity, str):
            try:
                quantity = int(quantity)
            except ValueError:
                return jsonify({"success": False, "error": "数量格式错误，请输入整数"}), 400
        if isinstance(price, str):
            try:
                price = float(price)
            except ValueError:
                return jsonify({"success": False, "error": "价格格式错误，请输入数字"}), 400

        if not stock_code:
            return jsonify({"success": False, "error": "股票代码不能为空"}), 400
        if not is_supported_stock_code(stock_code):
            return jsonify({"success": False, "error": "股票代码格式或代码段无效；基金请到基金交易页面操作"}), 400
        if not isinstance(quantity, int) or quantity <= 0:
            return jsonify({"success": False, "error": "卖出数量必须大于0"}), 400
        if quantity % 100 != 0:
            return jsonify({"success": False, "error": "卖出数量必须为100的整数倍"}), 400
        if not isinstance(price, (int, float)) or price <= 0:
            return jsonify({"success": False, "error": "价格必须大于0"}), 400
        if price > 10000:
            return jsonify({"success": False, "error": "价格异常（超过10000元），请核实后重试"}), 400

        # 检查持仓
        portfolio = Portfolio.query.filter_by(user_id=current_user.id, stock_code=stock_code).first()
        if not portfolio or portfolio.quantity < quantity:
            return jsonify({
                "success": False,
                "error": f"持仓不足。可卖出: {portfolio.quantity if portfolio else 0}股"
            }), 400

        # 计算金额
        total_amount = quantity * price
        commission = get_commission(total_amount)
        net_amount = total_amount - commission

        # 计算收益
        cost_basis = quantity * portfolio.avg_cost
        profit = net_amount - cost_basis

        # 更新持仓
        portfolio.quantity -= quantity
        portfolio.updated_at = datetime.now(timezone.utc)

        # 增加资金
        current_user.current_cash += net_amount

        # 记录交易
        trade = Trade(
            user_id=current_user.id,
            stock_code=stock_code,
            stock_name=portfolio.stock_name,
            action=Trade.ACTION_SELL,
            quantity=quantity,
            price=price,
            commission=commission,
            total_amount=total_amount,
            profit=profit,
        )
        db.session.add(trade)

        # 删除0持仓记录
        if portfolio.quantity == 0:
            db.session.delete(portfolio)

        db.session.commit()

        logger.info(f"用户 {current_user.id} 卖出 {stock_code} x {quantity} @ {price}, 收益: {profit:.2f}")

        return jsonify({
            "success": True,
            "message": f"卖出成功！\n股票: {portfolio.stock_name}\n数量: {quantity}股\n价格: {price:.2f}元\n手续费: {commission:.2f}元\n收益: {profit:.2f}元",
            "data": {
                "trade_id": trade.id,
                "stock_code": stock_code,
                "stock_name": portfolio.stock_name,
                "quantity": quantity,
                "price": price,
                "commission": commission,
                "net_amount": net_amount,
                "profit": profit,
                "remaining_cash": round(current_user.current_cash, 2),
            }
        })

    except Exception as e:
        db.session.rollback()
        logger.exception("卖出失败")
        return jsonify({"success": False, "error": f"卖出失败: {str(e)}"}), 500


@trade_bp.route("/api/reset", methods=["POST"])
@login_required
def reset_account():
    """重置模拟账户"""
    try:
        data = request.get_json()
        confirm = data.get("confirm", False)

        if not confirm:
            return jsonify({"success": False, "error": "请确认重置操作"}), 400

        user = current_user

        # 清空持仓
        Portfolio.query.filter_by(user_id=user.id).delete()
        FundPosition.query.filter_by(user_id=user.id).delete()

        # 清空交易记录
        Trade.query.filter_by(user_id=user.id).delete()
        FundTrade.query.filter_by(user_id=user.id).delete()
        FixedInvestment.query.filter_by(user_id=user.id).delete()

        # 重置资金
        user.current_cash = user.initial_cash
        user.frozen_cash = 0

        db.session.commit()

        logger.info(f"用户 {user.id} 重置了模拟账户")

        return jsonify({
            "success": True,
            "message": "账户已重置！",
            "data": {
                "initial_cash": user.initial_cash,
                "current_cash": user.current_cash,
            }
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@trade_bp.route("/api/set-initial-cash", methods=["POST"])
@login_required
def set_initial_cash():
    """设置初始资金"""
    try:
        data = request.get_json()
        amount = data.get("amount") or 0
        if isinstance(amount, str):
            amount = float(amount)

        if not isinstance(amount, (int, float)) or amount < 10000:
            return jsonify({"success": False, "error": "初始资金不能少于10000元"}), 400
        if amount > 100000000:
            return jsonify({"success": False, "error": "初始资金不能超过1亿元"}), 400

        user = current_user

        # 计算当前持仓市值
        snapshot = build_account_snapshot(user)
        positions = Portfolio.query.filter_by(user_id=user.id).filter(Portfolio.quantity > 0).all()
        total_assets = snapshot["total_assets"]

        # 更新初始资金
        user.initial_cash = amount

        # 按比例调整当前资金
        if total_assets > 0:
            ratio = amount / total_assets
            user.current_cash = user.current_cash * ratio
            for p in positions:
                p.avg_cost = p.avg_cost  # 保持成本不变，只调整资金

        db.session.commit()

        return jsonify({
            "success": True,
            "message": f"初始资金已设置为 {amount:.2f} 元",
            "data": {
                "initial_cash": user.initial_cash,
                "current_cash": round(user.current_cash, 2),
            }
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@trade_bp.route("/api/summary")
@login_required
def get_trading_summary():
    """获取交易统计（使用 SQL 聚合，避免全量加载到 Python）"""
    try:
        stats = db.session.query(
            func.count(Trade.id),
            func.sum(case((Trade.action == Trade.ACTION_BUY, 1), else_=0)),
            func.sum(case((Trade.action == Trade.ACTION_SELL, 1), else_=0)),
            func.coalesce(func.sum(Trade.commission), 0),
            func.coalesce(func.sum(case((Trade.profit.isnot(None), Trade.profit), else_=0)), 0),
            func.coalesce(func.sum(case((Trade.profit > 0, 1), else_=0)), 0),
            func.coalesce(func.sum(case((Trade.profit < 0, 1), else_=0)), 0),
        ).filter_by(user_id=current_user.id).first()

        total, buy_n, sell_n, commission, total_profit, win_n, loss_n = stats
        sell_n_val = sell_n or 0
        win_rate = win_n / sell_n_val * 100 if sell_n_val else 0

        return jsonify({
            "success": True,
            "data": {
                "total_trades": total or 0,
                "buy_count": buy_n or 0,
                "sell_count": sell_n_val,
                "total_commission": round(float(commission), 2),
                "total_profit": round(float(total_profit), 2),
                "win_count": win_n or 0,
                "loss_count": loss_n or 0,
                "win_rate": round(win_rate, 2),
            }
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
