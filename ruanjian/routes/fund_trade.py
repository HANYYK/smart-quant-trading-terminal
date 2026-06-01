"""
基金模拟交易路由 - 买入、卖出、定投管理
"""
from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user
from datetime import datetime, timezone
from sqlalchemy import desc
from sqlalchemy.exc import OperationalError
import logging
import re

from extensions import db
from models import FixedInvestment, FundPosition, FundTrade, Portfolio, Trade
from utils.accounting import build_account_snapshot

logger = logging.getLogger(__name__)
fund_trade_bp = Blueprint("fund_trade", __name__, url_prefix="/fund/trade")

# 默认手续费率（基金通常没有手续费或很低）
DEFAULT_COMMISSION_RATE = 0.0  # 前端基金一般免手续费

# 基金交易时间（模拟交易全天候开放）
TRADING_HOURS = {
    "start_hour": 9, "start_minute": 30,
    "end_am_hour": 11, "end_am_minute": 30,
    "start_pm_hour": 13, "start_pm_minute": 0,
    "end_hour": 15, "end_minute": 0
}

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


def normalize_fund_code(fund_code: str) -> str:
    """Keep only a valid six-digit fund code."""
    return re.sub(r"\D", "", str(fund_code or ""))[:6]


def is_valid_fund_name(name: str, fund_code: str = "") -> bool:
    """Reject long scraped disclaimers and other invalid fund names."""
    name = re.sub(r"\s+", " ", str(name or "")).strip()
    if not name or name == fund_code:
        return False
    if len(name) > 80:
        return False
    if any(keyword in name for keyword in INVALID_FUND_NAME_KEYWORDS):
        return False
    return True


def repair_fund_name(fund_code: str, current_name: str = "") -> str:
    """Return a safe fund name, refreshing it when stored data is invalid."""
    fund_code = normalize_fund_code(fund_code)
    if is_valid_fund_name(current_name, fund_code):
        return current_name
    info = get_fund_info(fund_code)
    fresh_name = info.get("name", "")
    return fresh_name if is_valid_fund_name(fresh_name, fund_code) else fund_code


def repair_user_fund_names(user_id: int) -> None:
    """Fix previously stored disclaimer text in fund positions/plans/trades."""
    repaired = False
    name_cache: dict[str, str] = {}
    for model in (FundPosition, FixedInvestment, FundTrade):
        try:
            rows = model.query.filter_by(user_id=user_id).all()
        except OperationalError as exc:
            db.session.rollback()
            logger.warning("跳过基金名称修复，表可能尚未初始化: %s", exc)
            continue
        for row in rows:
            code = normalize_fund_code(row.fund_code)
            if is_valid_fund_name(row.fund_name, code):
                continue
            if code not in name_cache:
                name_cache[code] = repair_fund_name(code, row.fund_name)
            safe_name = name_cache[code]
            if safe_name != row.fund_name:
                row.fund_name = safe_name
                repaired = True
    if repaired:
        db.session.commit()


def get_commission(amount: float, rate: float = DEFAULT_COMMISSION_RATE) -> float:
    """计算手续费"""
    return amount * rate


def can_trade() -> tuple[bool, str]:
    """检查是否可以交易（模拟交易全天候开放）"""
    return True, ""


def get_fund_nav(fund_code: str) -> tuple[float, float, str]:
    """获取基金净值和估算净值（周六日使用周五净值）"""
    try:
        from routes.fund import fetch_fund_realtime_data
        fund_code = normalize_fund_code(fund_code)
        now = datetime.now()

        # 周六日直接返回，因为基金净值周末不更新
        if now.weekday() >= 5:
            result = fetch_fund_realtime_data(fund_code)
            if result.get("success"):
                data = result.get("data", {})
                net_value = data.get("net_value", 0) or data.get("estimate_value", 0)
                estimate_value = data.get("estimate_value", 0)
                update_time = data.get("update_date", "")
                # 周末显示"周五净值"提示
                if update_time:
                    update_time = f"(周五净值) {update_time}"
                return float(net_value), float(estimate_value), update_time
        else:
            result = fetch_fund_realtime_data(fund_code)
            if result.get("success"):
                data = result.get("data", {})
                net_value = data.get("net_value", 0) or data.get("estimate_value", 0)
                estimate_value = data.get("estimate_value", 0)
                update_time = data.get("update_date", "")
                return float(net_value), float(estimate_value), update_time
    except Exception as e:
        logger.warning(f"获取基金净值失败 {fund_code}: {e}")
    return 0.0, 0.0, ""


def get_fund_info(fund_code: str) -> dict:
    """获取基金信息"""
    try:
        from routes.fund import fetch_fund_realtime_data, fetch_fund_info
        fund_code = normalize_fund_code(fund_code)
        realtime = fetch_fund_realtime_data(fund_code)
        info_result = fetch_fund_info(fund_code)

        fund_name = ""
        fund_type = ""

        if realtime.get("success"):
            realtime_name = realtime["data"].get("fund_name", "")
            if is_valid_fund_name(realtime_name, fund_code):
                fund_name = realtime_name

        if info_result.get("success"):
            info = info_result["data"]
            info_name = info.get("fund_name", "")
            if not fund_name and is_valid_fund_name(info_name, fund_code):
                fund_name = info_name
            fund_type = info.get("fund_type", "")

        nav, estimate_nav, update_time = get_fund_nav(fund_code)

        return {
            "code": fund_code,
            "name": fund_name or fund_code,
            "type": fund_type,
            "nav": nav,
            "estimate_nav": estimate_nav,
            "update_time": update_time,
            "can_trade": can_trade()[0],
            "trade_message": can_trade()[1],
        }
    except Exception as e:
        logger.warning(f"获取基金信息失败 {fund_code}: {e}")
        return {
            "code": fund_code,
            "name": fund_code,
            "type": "",
            "nav": 0,
            "estimate_nav": 0,
            "update_time": "",
            "can_trade": True,
            "trade_message": "",
        }


@fund_trade_bp.route("/")
@login_required
def index():
    """基金交易主页"""
    return render_template("fund_trade/index.html")


@fund_trade_bp.route("/position")
@login_required
def position():
    """基金持仓页面"""
    return render_template("fund_trade/position.html")


@fund_trade_bp.route("/fixed")
@login_required
def fixed():
    """定投管理页面"""
    return render_template("fund_trade/fixed.html")


@fund_trade_bp.route("/orders")
@login_required
def orders():
    """基金交易记录页面"""
    return render_template("fund_trade/orders.html")


@fund_trade_bp.route("/api/fund/quote/<fund_code>")
@login_required
def get_fund_quote(fund_code: str):
    """获取基金行情"""
    try:
        fund_code = normalize_fund_code(fund_code)
        if len(fund_code) != 6:
            return jsonify({"success": False, "error": "基金代码格式无效，请输入6位数字代码"}), 400
        info = get_fund_info(fund_code)

        # 检查是否持有
        position = FundPosition.query.filter_by(user_id=current_user.id, fund_code=fund_code).first()
        holding = None
        if position and position.total_shares > 0:
            current_nav = info["estimate_nav"] or info["nav"]
            if current_nav > 0:
                market_value = position.total_shares * current_nav
                profit = (current_nav - position.avg_cost) * position.total_shares
                profit_rate = (current_nav - position.avg_cost) / position.avg_cost * 100 if position.avg_cost > 0 else 0
                holding = {
                    "total_shares": round(position.total_shares, 2),
                    "avg_cost": round(position.avg_cost, 4),
                    "market_value": round(market_value, 2),
                    "profit": round(profit, 2),
                    "profit_rate": round(profit_rate, 2),
                }

        return jsonify({
            "success": True,
            "data": {
                "fund": info,
                "holding": holding,
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@fund_trade_bp.route("/api/account/info")
@login_required
def get_account_info():
    """获取基金账户信息"""
    try:
        repair_user_fund_names(current_user.id)
        snapshot = build_account_snapshot(current_user)

        return jsonify({
            "success": True,
            "data": {
                **snapshot,
                "position_value": snapshot["fund_position_value"],
                "position_count": snapshot["fund_position_count"],
                "positions": snapshot["fund_positions"],
            }
        })
    except Exception as e:
        logger.exception("获取基金账户信息失败")
        return jsonify({"success": False, "error": str(e)}), 500


@fund_trade_bp.route("/api/position/list")
@login_required
def get_position_list():
    """获取基金持仓列表"""
    try:
        positions = FundPosition.query.filter_by(user_id=current_user.id).filter(FundPosition.total_shares > 0).all()
        result = []
        repaired = False
        for p in positions:
            safe_name = repair_fund_name(p.fund_code, p.fund_name)
            if safe_name != p.fund_name:
                p.fund_name = safe_name
                repaired = True
            _, estimate_nav, _ = get_fund_nav(p.fund_code)
            current_nav = estimate_nav if estimate_nav > 0 else p.avg_cost
            market_value = p.total_shares * current_nav
            profit = (current_nav - p.avg_cost) * p.total_shares
            profit_rate = (current_nav - p.avg_cost) / p.avg_cost * 100 if p.avg_cost > 0 else 0
            result.append({
                "id": p.id,
                "fund_code": p.fund_code,
                "fund_name": safe_name,
                "total_shares": round(p.total_shares, 2),
                "avg_cost": round(p.avg_cost, 4),
                "current_nav": round(current_nav, 4),
                "market_value": round(market_value, 2),
                "profit": round(profit, 2),
                "profit_rate": round(profit_rate, 2),
            })
        if repaired:
            db.session.commit()
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@fund_trade_bp.route("/api/trade/list")
@login_required
def get_trade_list():
    """获取基金交易记录"""
    try:
        page = request.args.get("page", 1, type=int)
        page_size = request.args.get("page_size", 20, type=int)
        fund_code = request.args.get("fund_code", "")

        query = FundTrade.query.filter_by(user_id=current_user.id)
        if fund_code:
            query = query.filter_by(fund_code=fund_code)

        query = query.order_by(desc(FundTrade.created_at))
        pagination = query.paginate(page=page, per_page=page_size, error_out=False)

        trades = []
        repaired = False
        for t in pagination.items:
            safe_name = repair_fund_name(t.fund_code, t.fund_name)
            if safe_name != t.fund_name:
                t.fund_name = safe_name
                repaired = True
            trades.append({
                "id": t.id,
                "fund_code": t.fund_code,
                "fund_name": safe_name,
                "action": t.action,
                "trade_type": t.trade_type,
                "amount": round(t.amount, 2),
                "shares": round(t.shares, 2),
                "nav": round(t.nav, 4),
                "commission": round(t.commission, 2),
                "profit": round(t.profit, 2) if t.profit is not None else None,
                "created_at": t.created_at.strftime("%Y-%m-%d %H:%M"),
            })
        if repaired:
            db.session.commit()

        return jsonify({
            "success": True,
            "data": trades,
            "total": pagination.total,
            "pages": pagination.pages,
            "page": page,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@fund_trade_bp.route("/api/buy", methods=["POST"])
@login_required
def buy_fund():
    """买入基金"""
    try:
        data = request.get_json()
        fund_code = normalize_fund_code(data.get("fund_code") or "")
        amount = data.get("amount") or 0
        if isinstance(amount, str):
            amount = float(amount)

        if len(fund_code) != 6:
            return jsonify({"success": False, "error": "基金代码格式无效，请输入6位数字代码"}), 400
        if not isinstance(amount, (int, float)) or amount <= 0:
            return jsonify({"success": False, "error": "买入金额必须大于0"}), 400
        if amount < 10:
            return jsonify({"success": False, "error": "最低买入金额为10元"}), 400

        # 获取基金净值（失败时使用默认值1.0）
        nav, _, _ = get_fund_nav(fund_code)
        if nav <= 0:
            nav = 1.0  # 使用默认值避免买入失败

        fund_info = get_fund_info(fund_code)
        fund_name = fund_info.get("name", fund_code)

        # 计算份额
        commission = get_commission(amount)
        net_amount = amount - commission
        shares = net_amount / nav

        # 检查资金
        user = current_user
        if user.current_cash < amount:
            return jsonify({
                "success": False,
                "error": f"资金不足。需要 {amount:.2f}元，当前可用 {user.current_cash:.2f}元"
            }), 400

        # 更新持仓
        position = FundPosition.query.filter_by(user_id=user.id, fund_code=fund_code).first()
        if position:
            if not is_valid_fund_name(position.fund_name, fund_code):
                position.fund_name = fund_name
            total_invested = position.total_invested + amount
            total_shares = position.total_shares + shares
            position.avg_cost = total_invested / total_shares if total_shares > 0 else 0
            position.total_shares = total_shares
            position.total_invested = total_invested
            position.updated_at = datetime.now(timezone.utc)
        else:
            position = FundPosition(
                user_id=user.id,
                fund_code=fund_code,
                fund_name=fund_name,
                total_shares=shares,
                avg_cost=nav,
                total_invested=amount,
            )
            db.session.add(position)

        # 扣除资金
        user.current_cash -= amount

        # 记录交易
        trade = FundTrade(
            user_id=user.id,
            fund_code=fund_code,
            fund_name=fund_name,
            action=FundTrade.ACTION_BUY,
            trade_type=FundTrade.TYPE_DIRECT,
            amount=amount,
            shares=shares,
            nav=nav,
            commission=commission,
        )
        db.session.add(trade)
        db.session.commit()

        logger.info(f"用户 {user.id} 买入基金 {fund_code} x {amount}元")

        return jsonify({
            "success": True,
            "message": f"买入成功！\n基金: {fund_name}\n金额: {amount:.2f}元\n净值: {nav:.4f}\n份额: {shares:.2f}份",
            "data": {
                "trade_id": trade.id,
                "fund_code": fund_code,
                "fund_name": fund_name,
                "amount": amount,
                "shares": round(shares, 2),
                "nav": nav,
                "remaining_cash": round(user.current_cash, 2),
            }
        })

    except Exception as e:
        db.session.rollback()
        logger.exception("买入基金失败")
        return jsonify({"success": False, "error": f"买入失败: {str(e)}"}), 500


@fund_trade_bp.route("/api/sell", methods=["POST"])
@login_required
def sell_fund():
    """卖出基金"""
    try:
        data = request.get_json()
        fund_code = normalize_fund_code(data.get("fund_code") or "")
        shares = data.get("shares") or 0
        if isinstance(shares, str):
            shares = float(shares)

        if len(fund_code) != 6:
            return jsonify({"success": False, "error": "基金代码格式无效，请输入6位数字代码"}), 400
        if not isinstance(shares, (int, float)) or shares <= 0:
            return jsonify({"success": False, "error": "卖出份额必须大于0"}), 400

        # 检查持仓
        position = FundPosition.query.filter_by(user_id=current_user.id, fund_code=fund_code).first()
        if not position or position.total_shares < shares:
            return jsonify({
                "success": False,
                "error": f"持仓不足。可卖出: {position.total_shares if position else 0}份"
            }), 400

        # 获取基金净值
        nav, _, _ = get_fund_nav(fund_code)
        if nav <= 0:
            return jsonify({"success": False, "error": "无法获取基金净值"}), 400

        # 计算金额
        total_amount = shares * nav
        commission = get_commission(total_amount)
        net_amount = total_amount - commission

        # 计算收益
        cost_basis = shares * position.avg_cost
        profit = net_amount - cost_basis

        # 更新持仓
        position.total_shares -= shares
        position.total_invested = position.total_shares * position.avg_cost
        position.updated_at = datetime.now(timezone.utc)

        # 增加资金
        current_user.current_cash += net_amount

        # 记录交易
        trade = FundTrade(
            user_id=current_user.id,
            fund_code=fund_code,
            fund_name=position.fund_name,
            action=FundTrade.ACTION_SELL,
            trade_type=FundTrade.TYPE_DIRECT,
            amount=total_amount,
            shares=shares,
            nav=nav,
            commission=commission,
            profit=profit,
        )
        db.session.add(trade)

        # 删除0持仓记录
        if position.total_shares <= 0.01:  # 小数精度处理
            db.session.delete(position)

        db.session.commit()

        logger.info(f"用户 {current_user.id} 卖出基金 {fund_code} x {shares}份, 收益: {profit:.2f}")

        return jsonify({
            "success": True,
            "message": f"卖出成功！\n基金: {position.fund_name}\n份额: {shares:.2f}份\n净值: {nav:.4f}\n金额: {total_amount:.2f}元\n手续费: {commission:.2f}元\n收益: {profit:.2f}元",
            "data": {
                "trade_id": trade.id,
                "fund_code": fund_code,
                "fund_name": position.fund_name,
                "shares": round(shares, 2),
                "nav": nav,
                "net_amount": round(net_amount, 2),
                "profit": round(profit, 2),
                "remaining_cash": round(current_user.current_cash, 2),
            }
        })

    except Exception as e:
        db.session.rollback()
        logger.exception("卖出基金失败")
        return jsonify({"success": False, "error": f"卖出失败: {str(e)}"}), 500


@fund_trade_bp.route("/api/fixed/list")
@login_required
def get_fixed_list():
    """获取定投计划列表"""
    try:
        plans = FixedInvestment.query.filter_by(user_id=current_user.id).all()
        result = []
        repaired = False
        for p in plans:
            safe_name = repair_fund_name(p.fund_code, p.fund_name)
            if safe_name != p.fund_name:
                p.fund_name = safe_name
                repaired = True
            _, estimate_nav, _ = get_fund_nav(p.fund_code)
            current_nav = estimate_nav if estimate_nav > 0 else 1.0
            current_value = p.total_shares * current_nav
            profit = current_value - p.total_invested
            result.append({
                "id": p.id,
                "fund_code": p.fund_code,
                "fund_name": safe_name,
                "amount": round(p.amount, 2),
                "day": p.day,
                "status": p.status,
                "total_invested": round(p.total_invested, 2),
                "total_shares": round(p.total_shares, 2),
                "current_value": round(current_value, 2),
                "profit": round(profit, 2),
                "profit_rate": round(profit / p.total_invested * 100, 2) if p.total_invested > 0 else 0,
            })
        if repaired:
            db.session.commit()
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@fund_trade_bp.route("/api/fixed/create", methods=["POST"])
@login_required
def create_fixed_plan():
    """创建定投计划"""
    try:
        data = request.get_json()
        fund_code = normalize_fund_code(data.get("fund_code") or "")
        amount = data.get("amount") or 0
        day = data.get("day") or 1
        if isinstance(amount, str):
            amount = float(amount)
        if isinstance(day, str):
            day = int(day)

        if len(fund_code) != 6:
            return jsonify({"success": False, "error": "基金代码格式无效，请输入6位数字代码"}), 400
        if not isinstance(amount, (int, float)) or amount < 10:
            return jsonify({"success": False, "error": "定投金额不能少于10元"}), 400
        if not isinstance(day, int) or day < 1 or day > 28:
            return jsonify({"success": False, "error": "定投日必须在1-28之间"}), 400

        fund_info = get_fund_info(fund_code)
        fund_name = fund_info.get("name", fund_code)

        # 检查是否已有计划
        existing = FixedInvestment.query.filter_by(user_id=current_user.id, fund_code=fund_code).first()
        if existing:
            return jsonify({"success": False, "error": "该基金已有定投计划，请先终止原计划"}), 400

        plan = FixedInvestment(
            user_id=current_user.id,
            fund_code=fund_code,
            fund_name=fund_name,
            amount=amount,
            day=day,
            status=FixedInvestment.STATUS_ACTIVE,
        )
        db.session.add(plan)
        db.session.commit()

        return jsonify({
            "success": True,
            "message": f"定投计划创建成功！\n基金: {fund_name}\n每月{day}日定投 {amount:.2f}元",
            "data": {"id": plan.id}
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@fund_trade_bp.route("/api/fixed/<int:plan_id>", methods=["PUT"])
@login_required
def update_fixed_plan(plan_id: int):
    """更新定投计划"""
    try:
        plan = FixedInvestment.query.filter_by(id=plan_id, user_id=current_user.id).first()
        if not plan:
            return jsonify({"success": False, "error": "计划不存在"}), 404

        data = request.get_json()
        if "amount" in data:
            amount = data["amount"]
            if amount < 10:
                return jsonify({"success": False, "error": "定投金额不能少于10元"}), 400
            plan.amount = amount

        if "day" in data:
            day = data["day"]
            if day < 1 or day > 28:
                return jsonify({"success": False, "error": "定投日必须在1-28之间"}), 400
            plan.day = day

        if "status" in data:
            plan.status = data["status"]

        db.session.commit()

        return jsonify({
            "success": True,
            "message": "定投计划已更新",
            "data": {"amount": plan.amount, "day": plan.day, "status": plan.status}
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@fund_trade_bp.route("/api/fixed/<int:plan_id>", methods=["DELETE"])
@login_required
def delete_fixed_plan(plan_id: int):
    """删除定投计划"""
    try:
        plan = FixedInvestment.query.filter_by(id=plan_id, user_id=current_user.id).first()
        if not plan:
            return jsonify({"success": False, "error": "计划不存在"}), 404

        db.session.delete(plan)
        db.session.commit()

        return jsonify({"success": True, "message": "定投计划已删除"})

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@fund_trade_bp.route("/api/fixed/execute/<int:plan_id>", methods=["POST"])
@login_required
def execute_fixed_plan(plan_id: int):
    """执行定投（手动触发）"""
    try:
        plan = FixedInvestment.query.filter_by(id=plan_id, user_id=current_user.id).first()
        if not plan:
            return jsonify({"success": False, "error": "计划不存在"}), 404

        if plan.status != FixedInvestment.STATUS_ACTIVE:
            return jsonify({"success": False, "error": "计划已暂停或终止"}), 400

        # 获取净值
        nav, _, _ = get_fund_nav(plan.fund_code)
        if nav <= 0:
            return jsonify({"success": False, "error": "无法获取基金净值"}), 400

        amount = plan.amount

        # 检查资金
        user = current_user
        if user.current_cash < amount:
            return jsonify({"success": False, "error": f"资金不足，需要 {amount:.2f}元"}), 400

        # 计算份额
        shares = amount / nav

        # 更新持仓
        position = FundPosition.query.filter_by(user_id=user.id, fund_code=plan.fund_code).first()
        if position:
            position.total_invested += amount
            position.total_shares += shares
            position.avg_cost = position.total_invested / position.total_shares
            position.updated_at = datetime.now(timezone.utc)
        else:
            position = FundPosition(
                user_id=user.id,
                fund_code=plan.fund_code,
                fund_name=plan.fund_name,
                total_shares=shares,
                avg_cost=nav,
                total_invested=amount,
            )
            db.session.add(position)

        # 扣除资金
        user.current_cash -= amount

        # 更新定投计划
        plan.total_invested += amount
        plan.total_shares += shares

        # 记录交易
        trade = FundTrade(
            user_id=user.id,
            fund_code=plan.fund_code,
            fund_name=plan.fund_name,
            action=FundTrade.ACTION_BUY,
            trade_type=FundTrade.TYPE_FIXED,
            amount=amount,
            shares=shares,
            nav=nav,
            commission=0,
        )
        db.session.add(trade)
        db.session.commit()

        return jsonify({
            "success": True,
            "message": f"定投执行成功！\n基金: {plan.fund_name}\n金额: {amount:.2f}元\n净值: {nav:.4f}\n份额: {shares:.2f}份",
            "data": {
                "amount": amount,
                "shares": round(shares, 2),
                "nav": nav,
            }
        })

    except Exception as e:
        db.session.rollback()
        logger.exception("定投执行失败")
        return jsonify({"success": False, "error": str(e)}), 500


@fund_trade_bp.route("/api/summary")
@login_required
def get_trading_summary():
    """获取基金交易统计"""
    try:
        trades = FundTrade.query.filter_by(user_id=current_user.id).all()

        buy_count = sum(1 for t in trades if t.action == FundTrade.ACTION_BUY)
        sell_count = sum(1 for t in trades if t.action == FundTrade.ACTION_SELL)
        fixed_count = sum(1 for t in trades if t.trade_type == FundTrade.TYPE_FIXED)
        total_invested = sum(t.amount for t in trades if t.action == FundTrade.ACTION_BUY)

        sell_trades = [t for t in trades if t.action == FundTrade.ACTION_SELL and t.profit is not None]
        total_profit = sum(t.profit for t in sell_trades)

        return jsonify({
            "success": True,
            "data": {
                "total_trades": len(trades),
                "buy_count": buy_count,
                "sell_count": sell_count,
                "fixed_count": fixed_count,
                "total_invested": round(total_invested, 2),
                "total_profit": round(total_profit, 2),
            }
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@fund_trade_bp.route("/api/deposit", methods=["POST"])
@login_required
def deposit():
    """充值（模拟）"""
    try:
        data = request.get_json()
        amount = data.get("amount") or 0
        if isinstance(amount, str):
            amount = float(amount)
        elif not isinstance(amount, (int, float)):
            amount = 0

        if amount <= 0:
            return jsonify({"success": False, "error": "充值金额必须大于0"}), 400
        if amount > 1000000:
            return jsonify({"success": False, "error": "单次充值上限100万元"}), 400

        current_user.current_cash += amount
        current_user.initial_cash += amount
        db.session.commit()

        logger.info(f"用户 {current_user.id} 充值 {amount:.2f}元")

        return jsonify({
            "success": True,
            "message": f"充值成功！\n充值金额: {amount:.2f}元\n当前余额: {current_user.current_cash:.2f}元",
            "data": {
                "deposit_amount": amount,
                "available_cash": round(current_user.current_cash, 2),
            }
        })

    except Exception as e:
        db.session.rollback()
        logger.exception("充值失败")
        return jsonify({"success": False, "error": str(e)}), 500


@fund_trade_bp.route("/api/reset", methods=["POST"])
@login_required
def reset_account():
    """重置账户（模拟）"""
    try:
        user = current_user
        initial = user.initial_cash

        # 清空所有模拟持仓和交易记录。股票/基金共用现金账户，需同一口径重置。
        Portfolio.query.filter_by(user_id=user.id).delete()
        Trade.query.filter_by(user_id=user.id).delete()
        FundPosition.query.filter_by(user_id=user.id).delete()
        FundTrade.query.filter_by(user_id=user.id).delete()
        FixedInvestment.query.filter_by(user_id=user.id).delete()

        # 重置资金
        user.current_cash = initial

        db.session.commit()
        logger.info(f"用户 {user.id} 重置账户")

        return jsonify({
            "success": True,
            "message": f"账户已重置！\n初始资金: {initial:.2f}元\n当前余额: {user.current_cash:.2f}元",
            "data": {
                "initial_cash": initial,
                "current_cash": round(user.current_cash, 2),
            }
        })

    except Exception as e:
        db.session.rollback()
        logger.exception("账户重置失败")
        return jsonify({"success": False, "error": str(e)}), 500
