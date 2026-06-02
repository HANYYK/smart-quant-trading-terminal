"""
智能量化交易终端 - Flask 应用核心配置
Python 3.11+ 适配
"""
import os
import logging
from datetime import datetime, timedelta, timezone
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from werkzeug.middleware.proxy_fix import ProxyFix

load_dotenv()

from extensions import db, login_manager, migrate, csrf, limiter
from utils.logging_config import setup_logging


def create_app(config_name: str = "default") -> Flask:
    if config_name == "default":
        config_name = os.environ.get("FLASK_ENV", "development").lower()
    if config_name not in config_mapping:
        raise ValueError(f"Unknown config name: {config_name}")

    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
        static_url_path="/static"
    )

    app.config.from_object(config_mapping[config_name])
    if app.config.get("PREFERRED_URL_SCHEME") == "https":
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    setup_logging(app)

    # 安全检查：生产环境必须设置 SECRET_KEY
    if config_name == "production" and (
        not app.config.get("SECRET_KEY")
        or app.config.get("SECRET_KEY") == "your-super-secret-key-change-this-in-production"
        or app.config.get("SECRET_KEY") == "change-this-before-production"
    ):
        raise ValueError(
            "SECRET_KEY environment variable must be set in production. "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )

    if config_name == "production" and not app.config.get("SQLALCHEMY_DATABASE_URI"):
        raise ValueError("DATABASE_URL environment variable must be set in production.")

    if config_name == "development" and not os.environ.get("SECRET_KEY"):
        logging.warning(
            "SECRET_KEY not set in .env file. "
            "Using default key - NOT SUITABLE FOR PRODUCTION!"
        )

    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    login_manager.init_app(app)
    limiter.init_app(app)

    login_manager.login_view = "auth.login"
    login_manager.login_message = "请登录后访问"
    login_manager.refresh_view = "auth.login"
    login_manager.session_protection = "strong"

    register_error_handlers(app)
    register_hooks(app)
    register_health_endpoints(app)

    # Import models before create_all so SQLAlchemy metadata includes every table.
    from models import User

    with app.app_context():
        try:
            db.create_all()
            app.logger.info("数据库初始化成功")
        except Exception as e:
            app.logger.error(f"数据库初始化失败: {e}")

        # 迁移检查：确保 users 表有所有新字段
        _ensure_user_columns(app)
        _ensure_trade_tables(app)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    from routes.auth_routes import auth_bp
    from routes.stock import stock_bp
    from routes.fund import fund_bp
    from routes.dashboard import dashboard_bp
    from routes.market import market_bp
    from routes.trade import trade_bp
    from routes.fund_trade import fund_trade_bp

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(stock_bp, url_prefix="/stock")
    app.register_blueprint(fund_bp, url_prefix="/fund")
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(market_bp, url_prefix="/market")
    app.register_blueprint(trade_bp, url_prefix="/trade")
    app.register_blueprint(fund_trade_bp, url_prefix="/fund/trade")

    if not app.config.get("TESTING"):
        try:
            from utils.shared_cache import warmup_stock_cache
            warmup_stock_cache()
            app.logger.info("市场数据缓存预热完成")
        except Exception:
            pass

    app.logger.info(f"应用启动成功 - 环境: {config_name}")

    return app


def register_error_handlers(app: Flask) -> None:
    """注册全局错误处理器"""
    @app.errorhandler(404)
    def not_found(error):
        if request.is_json:
            return jsonify({"success": False, "error": "资源未找到"}), 404
        return error.description, 404

    @app.errorhandler(500)
    def internal_error(error):
        err_msg = str(error)
        logging.exception("500 Internal Server Error: %s", err_msg)
        db.session.rollback()
        if request.is_json or request.blueprint:
            return jsonify({
                "success": False,
                "error": f"服务器内部错误: {err_msg}"
            }), 500
        return f"服务器内部错误: {err_msg}", 500

    @app.errorhandler(429)
    def rate_limited(error):
        if request.is_json:
            return jsonify({
                "success": False,
                "error": "请求过于频繁，请稍后再试"
            }), 429
        return "请求过于频繁", 429

    @app.errorhandler(403)
    def forbidden(error):
        if request.is_json:
            return jsonify({"success": False, "error": "禁止访问"}), 403
        return "禁止访问", 403

    @app.errorhandler(400)
    def bad_request(error):
        if request.is_json:
            return jsonify({"success": False, "error": "请求参数错误"}), 400
        return "请求参数错误", 400


def register_hooks(app: Flask) -> None:
    """注册请求钩子"""
    @app.before_request
    def before_request():
        """请求前处理"""
        from flask import g
        g.request_start_time = datetime.now(timezone.utc)
        g.client_ip = request.remote_addr

    @app.after_request
    def after_request(response):
        """响应后处理"""
        # 安全头
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        if app.config.get("PREFERRED_URL_SCHEME") == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        # 请求耗时
        from flask import g
        if hasattr(g, "request_start_time"):
            elapsed = (datetime.now(timezone.utc) - g.request_start_time).total_seconds() * 1000
            response.headers["X-Response-Time"] = f"{elapsed:.2f}ms"

        # CORS 头（仅 API 端点）
        if request.path.startswith("/api/"):
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-CSRF-Token"

        return response


def _ensure_user_columns(app: Flask) -> None:
    """确保 users 表有所有新字段（向后兼容迁移）"""
    from models import User
    inspector = db.inspect(db.engine)
    try:
        columns = [col["name"] for col in inspector.get_columns("users")]
        new_columns = {
            "initial_cash": {"type": "Float", "default": 1000000.0},
            "current_cash": {"type": "Float", "default": 1000000.0},
            "frozen_cash": {"type": "Float", "default": 0.0},
        }
        for col_name, col_info in new_columns.items():
            if col_name not in columns:
                app.logger.warning(f"检测到缺失列 {col_name}，正在添加...")
                db.session.execute(
                    db.text(f"ALTER TABLE users ADD COLUMN {col_name} {col_info['type']} DEFAULT {col_info['default']}")
                )
                db.session.commit()
                app.logger.info(f"成功添加列 {col_name}")
    except Exception as e:
        app.logger.warning(f"迁移检查跳过: {e}")


def _ensure_trade_tables(app: Flask) -> None:
    """确保交易相关表存在"""
    from models import Portfolio, Trade, TradingSummary, FundPosition, FundTrade
    inspector = db.inspect(db.engine)
    try:
        existing_tables = inspector.get_table_names()
        required_tables = [
            "portfolios",
            "trades",
            "trading_summaries",
            "fund_positions",
            "fund_trades",
            "fixed_investments",
        ]
        for table_name in required_tables:
            if table_name not in existing_tables:
                app.logger.warning(f"检测到缺失表 {table_name}，正在创建...")
                # 使用 SQL 直接创建表
                table_map = {
                    "portfolios": """
                        CREATE TABLE IF NOT EXISTS portfolios (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id INTEGER NOT NULL,
                            stock_code VARCHAR(20) NOT NULL,
                            stock_name VARCHAR(50) NOT NULL,
                            quantity INTEGER NOT NULL DEFAULT 0,
                            avg_cost FLOAT NOT NULL DEFAULT 0.0,
                            created_at DATETIME NOT NULL,
                            updated_at DATETIME NOT NULL,
                            FOREIGN KEY (user_id) REFERENCES users (id)
                        )
                    """,
                    "trades": """
                        CREATE TABLE IF NOT EXISTS trades (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id INTEGER NOT NULL,
                            stock_code VARCHAR(20) NOT NULL,
                            stock_name VARCHAR(50) NOT NULL,
                            action VARCHAR(10) NOT NULL,
                            quantity INTEGER NOT NULL,
                            price FLOAT NOT NULL,
                            commission FLOAT NOT NULL DEFAULT 0.0,
                            total_amount FLOAT NOT NULL,
                            profit FLOAT,
                            created_at DATETIME NOT NULL,
                            FOREIGN KEY (user_id) REFERENCES users (id)
                        )
                    """,
                    "trading_summaries": """
                        CREATE TABLE IF NOT EXISTS trading_summaries (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id INTEGER NOT NULL,
                            date DATE NOT NULL,
                            total_value FLOAT NOT NULL DEFAULT 0.0,
                            cash FLOAT NOT NULL DEFAULT 0.0,
                            position_value FLOAT NOT NULL DEFAULT 0.0,
                            profit FLOAT NOT NULL DEFAULT 0.0,
                            profit_rate FLOAT NOT NULL DEFAULT 0.0,
                            created_at DATETIME NOT NULL,
                            FOREIGN KEY (user_id) REFERENCES users (id)
                        )
                    """,
                    "fund_positions": """
                        CREATE TABLE IF NOT EXISTS fund_positions (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id INTEGER NOT NULL,
                            fund_code VARCHAR(20) NOT NULL,
                            fund_name VARCHAR(50) NOT NULL,
                            total_shares FLOAT NOT NULL DEFAULT 0.0,
                            avg_cost FLOAT NOT NULL DEFAULT 0.0,
                            total_invested FLOAT NOT NULL DEFAULT 0.0,
                            created_at DATETIME NOT NULL,
                            updated_at DATETIME NOT NULL,
                            FOREIGN KEY (user_id) REFERENCES users (id)
                        )
                    """,
                    "fund_trades": """
                        CREATE TABLE IF NOT EXISTS fund_trades (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id INTEGER NOT NULL,
                            fund_code VARCHAR(20) NOT NULL,
                            fund_name VARCHAR(50) NOT NULL,
                            action VARCHAR(10) NOT NULL,
                            trade_type VARCHAR(20) DEFAULT 'direct',
                            shares FLOAT NOT NULL,
                            nav FLOAT NOT NULL,
                            amount FLOAT NOT NULL,
                            commission FLOAT NOT NULL DEFAULT 0.0,
                            profit FLOAT,
                            created_at DATETIME NOT NULL,
                            FOREIGN KEY (user_id) REFERENCES users (id)
                        )
                    """,
                    "fixed_investments": """
                        CREATE TABLE IF NOT EXISTS fixed_investments (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id INTEGER NOT NULL,
                            fund_code VARCHAR(20) NOT NULL,
                            fund_name VARCHAR(100) NOT NULL,
                            amount FLOAT NOT NULL,
                            day INTEGER NOT NULL DEFAULT 1,
                            status VARCHAR(20) NOT NULL DEFAULT 'active',
                            total_invested FLOAT NOT NULL DEFAULT 0.0,
                            total_shares FLOAT NOT NULL DEFAULT 0.0,
                            created_at DATETIME NOT NULL,
                            updated_at DATETIME NOT NULL,
                            FOREIGN KEY (user_id) REFERENCES users (id)
                        )
                    """
                }
                if table_name in table_map:
                    db.session.execute(db.text(table_map[table_name]))
                    db.session.commit()
                    app.logger.info(f"成功创建表 {table_name}")
                else:
                    app.logger.warning(f"未知的表: {table_name}")
            else:
                app.logger.info(f"表已存在: {table_name}")

        _ensure_trade_table_columns(app, inspector)
    except Exception as e:
        app.logger.warning(f"交易表检查跳过: {e}")


def _ensure_trade_table_columns(app: Flask, inspector) -> None:
    """为旧版本 SQLite 表补齐新增列。"""
    column_specs = {
        "fund_trades": {
            "trade_type": "VARCHAR(20) DEFAULT 'direct'",
            "profit": "FLOAT",
        },
        "trades": {
            "profit": "FLOAT",
        },
        "fund_positions": {
            "total_invested": "FLOAT NOT NULL DEFAULT 0.0",
        },
    }

    for table_name, columns in column_specs.items():
        try:
            existing_columns = {col["name"] for col in inspector.get_columns(table_name)}
            for column_name, column_type in columns.items():
                if column_name not in existing_columns:
                    app.logger.warning(f"检测到 {table_name}.{column_name} 缺失，正在添加...")
                    db.session.execute(
                        db.text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
                    )
                    db.session.commit()
                    app.logger.info(f"成功添加列 {table_name}.{column_name}")
        except Exception as e:
            app.logger.warning(f"表 {table_name} 列检查跳过: {e}")


def register_health_endpoints(app: Flask) -> None:
    """注册健康检查端点"""
    @app.route("/health")
    def health_check():
        """健康检查端点"""
        health_status = {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": "1.0.0"
        }

        # 检查数据库连接
        try:
            db.session.execute(db.text("SELECT 1"))
            health_status["database"] = "connected"
        except Exception as e:
            health_status["database"] = "disconnected"
            health_status["status"] = "degraded"

        return jsonify(health_status)

    @app.route("/ready")
    def readiness_check():
        """就绪检查端点（用于 Kubernetes）"""
        try:
            db.session.execute(db.text("SELECT 1"))
            return jsonify({"ready": True}), 200
        except Exception:
            return jsonify({"ready": False}), 503


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY")
    WTF_CSRF_TIME_LIMIT = 3600  # CSRF token 有效期 1 小时
    WTF_CSRF_HEADERS = ["X-CSRFToken", "X-CSRF-Token"]  # 支持多种 CSRF 头
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "pool_size": 10,
        "max_overflow": 20,
    }
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    JSON_AS_ASCII = False  # 支持中文 JSON
    JSONIFY_PRETTYPRINT_REGULAR = True
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB 最大请求大小
    # 日志配置
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
    LOG_FILE = os.environ.get("LOG_FILE", "logs/app.log")


class DevelopmentConfig(Config):
    DEBUG = True
    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-secret-key-change-in-production"
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL"
    ) or "sqlite:///quant_trading.db"
    # SQLAlchemy 日志（开发环境）
    SQLALCHEMY_ECHO = False


class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    # 生产环境强制 HTTPS
    PREFERRED_URL_SCHEME = "https"


class TestingConfig(Config):
    TESTING = True
    SECRET_KEY = "test-secret-key-for-testing-only"
    WTF_CSRF_ENABLED = False  # 禁用CSRF用于测试
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {
        "poolclass": __import__("sqlalchemy.pool", fromlist=["StaticPool"]).StaticPool,
        "connect_args": {"check_same_thread": False},
    }


config_mapping = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}

if __name__ == "__main__":
    application = create_app(os.environ.get("FLASK_ENV", "development"))
    application.run(host="0.0.0.0", port=5000, threaded=True)
