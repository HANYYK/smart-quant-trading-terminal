"""
数据库模型 - 解决循环导入问题
"""
import re
import secrets
from datetime import datetime, timezone
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import Index
from extensions import db


class User(UserMixin, db.Model):
    """用户模型"""
    __tablename__ = "users"

    # 角色常量
    ROLE_ADMIN = "admin"
    ROLE_USER = "user"
    ROLE_VIP = "vip"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=True, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    last_login = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    role = db.Column(db.String(20), default=ROLE_USER, nullable=False, index=True)

    # 邮箱验证
    email_verified = db.Column(db.Boolean, default=False, nullable=False)
    email_verification_token = db.Column(db.String(64), nullable=True)

    # 密码重置
    password_reset_token = db.Column(db.String(64), nullable=True)
    password_reset_expires = db.Column(db.DateTime, nullable=True)

    # 模拟交易账户
    initial_cash = db.Column(db.Float, default=1000000.0, nullable=False)  # 初始模拟资金
    current_cash = db.Column(db.Float, default=1000000.0, nullable=False)  # 当前可用资金
    frozen_cash = db.Column(db.Float, default=0.0, nullable=False)  # 冻结资金（挂单中）

    __table_args__ = (
        Index("ix_users_created_at", "created_at"),
        Index("ix_users_active_role", "is_active", "role"),
    )

    def set_password(self, password: str) -> None:
        """设置密码（自动验证强度）"""
        if not self._validate_password(password):
            raise ValueError("密码不符合安全要求：需包含字母和数字，至少8个字符")
        self.password_hash = generate_password_hash(password)

    @staticmethod
    def _validate_password(password: str) -> bool:
        """验证密码强度"""
        if len(password) < 8:
            return False
        if not re.search(r"[A-Za-z]", password):
            return False
        if not re.search(r"\d", password):
            return False
        return True

    def check_password(self, password: str) -> bool:
        """验证密码"""
        return check_password_hash(self.password_hash, password)

    def update_last_login(self) -> None:
        """更新最后登录时间"""
        self.last_login = datetime.now(timezone.utc)
        db.session.commit()

    def generate_email_verification_token(self) -> str:
        """生成邮箱验证令牌"""
        self.email_verification_token = secrets.token_urlsafe(32)
        db.session.commit()
        return self.email_verification_token

    def verify_email(self) -> bool:
        """验证邮箱"""
        if self.email_verified:
            return False
        self.email_verified = True
        self.email_verification_token = None
        db.session.commit()
        return True

    def generate_password_reset_token(self, expires_hours: int = 24) -> str:
        """生成密码重置令牌"""
        self.password_reset_token = secrets.token_urlsafe(32)
        self.password_reset_expires = datetime.now(timezone.utc) + timedelta(hours=expires_hours)
        db.session.commit()
        return self.password_reset_token

    def reset_password(self, new_password: str) -> bool:
        """重置密码"""
        if not self.password_reset_token or not self.password_reset_expires:
            return False
        if datetime.now(timezone.utc) > self.password_reset_expires:
            return False
        self.set_password(new_password)
        self.password_reset_token = None
        self.password_reset_expires = None
        db.session.commit()
        return True

    def is_admin(self) -> bool:
        """检查是否为管理员"""
        return self.role == self.ROLE_ADMIN

    def is_vip(self) -> bool:
        """检查是否为VIP用户"""
        return self.role in (self.ROLE_VIP, self.ROLE_ADMIN)

    def __repr__(self):
        return f"<User {self.username}>"


class LoginAttempt(db.Model):
    """登录尝试记录（用于暴力破解防护）"""
    __tablename__ = "login_attempts"

    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(45), nullable=False, index=True)
    username = db.Column(db.String(80), nullable=True, index=True)
    attempted_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    success = db.Column(db.Boolean, default=False)

    __table_args__ = (
        Index("ix_login_attempts_ip_time", "ip_address", "attempted_at"),
    )


class Portfolio(db.Model):
    """持仓记录"""
    __tablename__ = "portfolios"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    stock_code = db.Column(db.String(20), nullable=False, index=True)  # 股票代码: sh.600000
    stock_name = db.Column(db.String(50), nullable=False)  # 股票名称
    quantity = db.Column(db.Integer, nullable=False, default=0)  # 持有数量
    avg_cost = db.Column(db.Float, nullable=False, default=0.0)  # 平均成本
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                          onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("ix_portfolio_user_stock", "user_id", "stock_code", unique=True),
    )

    @property
    def total_cost(self) -> float:
        """总成本"""
        return self.quantity * self.avg_cost

    def __repr__(self):
        return f"<Portfolio {self.user_id}:{self.stock_code} x {self.quantity}>"


class Trade(db.Model):
    """交易记录"""
    __tablename__ = "trades"

    # 交易方向常量
    ACTION_BUY = "buy"
    ACTION_SELL = "sell"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    stock_code = db.Column(db.String(20), nullable=False, index=True)
    stock_name = db.Column(db.String(50), nullable=False)
    action = db.Column(db.String(10), nullable=False)  # buy/sell
    quantity = db.Column(db.Integer, nullable=False)  # 成交数量
    price = db.Column(db.Float, nullable=False)  # 成交价格
    commission = db.Column(db.Float, nullable=False, default=0.0)  # 手续费
    total_amount = db.Column(db.Float, nullable=False)  # 总金额（含手续费）
    profit = db.Column(db.Float, nullable=True)  # 卖出时的收益
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    __table_args__ = (
        Index("ix_trade_user_time", "user_id", "created_at"),
        Index("ix_trade_user_stock", "user_id", "stock_code"),
    )

    @property
    def is_profit(self) -> bool:
        """是否盈利"""
        return self.profit is not None and self.profit > 0

    def __repr__(self):
        return f"<Trade {self.user_id}:{self.action} {self.stock_code} x {self.quantity}>"


class TradingSummary(db.Model):
    """交易汇总（每日统计）"""
    __tablename__ = "trading_summaries"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False, index=True)
    total_value = db.Column(db.Float, nullable=False)  # 总资产（现金+持仓市值）
    cash = db.Column(db.Float, nullable=False)  # 可用资金
    position_value = db.Column(db.Float, nullable=False)  # 持仓市值
    profit = db.Column(db.Float, nullable=False)  # 当日收益
    profit_rate = db.Column(db.Float, nullable=False)  # 当日收益率
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("ix_summary_user_date", "user_id", "date", unique=True),
    )


class FundPosition(db.Model):
    """基金持仓记录"""
    __tablename__ = "fund_positions"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    fund_code = db.Column(db.String(20), nullable=False, index=True)  # 基金代码
    fund_name = db.Column(db.String(100), nullable=False)  # 基金名称
    total_shares = db.Column(db.Float, nullable=False, default=0.0)  # 总份额
    avg_cost = db.Column(db.Float, nullable=False, default=0.0)  # 平均成本（每份）
    total_invested = db.Column(db.Float, nullable=False, default=0.0)  # 总投入金额
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                          onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("ix_fund_position_user_fund", "user_id", "fund_code", unique=True),
    )

    def __repr__(self):
        return f"<FundPosition {self.user_id}:{self.fund_code} x {self.total_shares}>"


class FundTrade(db.Model):
    """基金交易记录"""
    __tablename__ = "fund_trades"

    # 交易方向
    ACTION_BUY = "buy"
    ACTION_SELL = "sell"
    ACTION_DIVIDEND = "dividend"  # 分红

    # 交易方式
    TYPE_DIRECT = "direct"  # 直接购买
    TYPE_FIXED = "fixed"  # 定投

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    fund_code = db.Column(db.String(20), nullable=False, index=True)
    fund_name = db.Column(db.String(100), nullable=False)
    action = db.Column(db.String(20), nullable=False)  # buy/sell/dividend
    trade_type = db.Column(db.String(20), default=TYPE_DIRECT)  # direct/fixed
    amount = db.Column(db.Float, nullable=False)  # 投入/赎回金额
    shares = db.Column(db.Float, nullable=False)  # 买入/卖出份额
    nav = db.Column(db.Float, nullable=False)  # 交易净值
    commission = db.Column(db.Float, nullable=False, default=0.0)  # 手续费
    profit = db.Column(db.Float, nullable=True)  # 赎回时的收益
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    __table_args__ = (
        Index("ix_fund_trade_user_time", "user_id", "created_at"),
        Index("ix_fund_trade_user_fund", "user_id", "fund_code"),
    )

    def __repr__(self):
        return f"<FundTrade {self.user_id}:{self.action} {self.fund_code} x {self.shares}>"


class FixedInvestment(db.Model):
    """定投计划"""
    __tablename__ = "fixed_investments"

    STATUS_ACTIVE = "active"
    STATUS_PAUSED = "paused"
    STATUS_STOPPED = "stopped"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    fund_code = db.Column(db.String(20), nullable=False)
    fund_name = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Float, nullable=False)  # 每月定投金额
    day = db.Column(db.Integer, nullable=False, default=1)  # 每月定投日(1-28)
    status = db.Column(db.String(20), default=STATUS_ACTIVE, nullable=False)
    total_invested = db.Column(db.Float, nullable=False, default=0.0)  # 累计投入
    total_shares = db.Column(db.Float, nullable=False, default=0.0)  # 累计份额
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                          onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("ix_fixed_user_fund", "user_id", "fund_code", unique=True),
    )

    def __repr__(self):
        return f"<FixedInvestment {self.user_id}:{self.fund_code} @ {self.amount}/month>"


from datetime import timedelta
