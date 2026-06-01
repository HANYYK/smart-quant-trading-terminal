"""
基础测试用例
"""
import pytest
from datetime import datetime, timezone
from app import create_app
from extensions import db
from models import User


@pytest.fixture
def app():
    """创建测试应用"""
    app = create_app("testing")

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    """创建测试客户端"""
    return app.test_client()


@pytest.fixture
def runner(app):
    """创建测试 CLI runner"""
    return app.test_cli_runner()


class TestUserModel:
    """用户模型测试"""

    def test_create_user(self, app):
        """测试创建用户"""
        with app.app_context():
            user = User(username="testuser")
            user.set_password("Test1234")
            db.session.add(user)
            db.session.commit()

            assert user.id is not None
            assert user.username == "testuser"
            assert user.password_hash != "Test1234"
            assert user.check_password("Test1234")

    def test_password_validation(self, app):
        """测试密码验证"""
        with app.app_context():
            user = User(username="testuser")

            # 有效密码
            user.set_password("Valid123")
            assert user.password_hash is not None

            # 无效密码 - 太短
            with pytest.raises(ValueError):
                user.set_password("Short1")

            # 无效密码 - 无字母
            with pytest.raises(ValueError):
                user.set_password("12345678")

            # 无效密码 - 无数字
            with pytest.raises(ValueError):
                user.set_password("abcdefgh")

    def test_user_roles(self, app):
        """测试用户角色"""
        with app.app_context():
            user = User(username="testuser", role=User.ROLE_USER)
            assert not user.is_admin()
            assert not user.is_vip()

            user.role = User.ROLE_ADMIN
            assert user.is_admin()
            assert user.is_vip()

            user.role = User.ROLE_VIP
            assert not user.is_admin()
            assert user.is_vip()


class TestHealthEndpoints:
    """健康检查端点测试"""

    def test_health_check(self, client):
        """测试健康检查端点"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "healthy"
        assert "database" in data
        assert data["database"] == "connected"

    def test_readiness_check(self, client):
        """测试就绪检查端点"""
        response = client.get("/ready")
        assert response.status_code == 200
        data = response.get_json()
        assert data["ready"] is True


class TestAuthRoutes:
    """认证路由测试"""

    def test_login_page(self, client):
        """测试登录页面"""
        response = client.get("/auth/login")
        assert response.status_code == 200

    def test_register_page(self, client):
        """测试注册页面"""
        response = client.get("/auth/register")
        assert response.status_code == 200

    def test_register_validation(self, client):
        """测试注册验证"""
        # 密码太短
        response = client.post("/auth/register", data={
            "username": "testuser",
            "password": "short",
            "password_confirm": "short"
        }, follow_redirects=False)
        assert response.status_code == 200
        assert "\u5bc6\u7801\u81f3\u5c11\u9700\u8981".encode("utf-8") in response.data

    def test_successful_registration(self, client):
        """测试成功注册"""
        response = client.post("/auth/register", data={
            "username": "newuser",
            "password": "Valid123",
            "password_confirm": "Valid123"
        }, follow_redirects=True)
        assert response.status_code == 200


class TestStockRoutes:
    """股票路由测试"""

    def test_stock_detail_page(self, client):
        """测试股票详情页"""
        response = client.get("/stock/detail/sh.600016")
        assert response.status_code == 200

    def test_invalid_stock_code(self, client):
        """测试无效股票代码"""
        response = client.get("/stock/detail/invalid")
        assert response.status_code == 200  # 会显示默认股票

    def test_stock_compare_page(self, client):
        """测试股票对比页"""
        response = client.get("/stock/compare")
        assert response.status_code == 200


class TestFundRoutes:
    """基金路由测试"""

    def test_fund_search_page(self, client):
        """测试基金搜索页"""
        response = client.get("/fund/search")
        assert response.status_code == 200

    def test_fund_ranking_page(self, client):
        """测试基金排行页"""
        response = client.get("/fund/ranking")
        assert response.status_code == 200
