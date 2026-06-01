"""
注册和登录功能测试
测试路由: /auth/register, /auth/login, /auth/logout, /auth/profile
"""
import pytest
from app import db
from models import User


def get_text(response):
    return response.data.decode("utf-8")


def contains_text(response, text):
    return text.encode("utf-8") in response.data


class TestRegisterPage:
    """测试注册页面"""

    def test_register_page_loads(self, client):
        response = client.get("/auth/register")
        assert response.status_code == 200
        assert "用户注册" in get_text(response)

    def test_register_page_accessible_when_logged_out(self, client):
        response = client.get("/auth/register")
        assert response.status_code == 200

    def test_register_page_redirect_when_logged_in(self, authenticated_client):
        response = authenticated_client.get("/auth/register", follow_redirects=False)
        assert response.status_code == 302


class TestRegisterFunctionality:
    """测试注册功能"""

    def test_register_success(self, client, app):
        with app.app_context():
            response = client.post("/auth/register", data={
                "username": "newuser",
                "password": "password123",
                "password_confirm": "password123",
            }, follow_redirects=True)

            assert response.status_code == 200
            text = get_text(response)
            assert "用户注册" not in text

            user = User.query.filter_by(username="newuser").first()
            assert user is not None
            assert user.username == "newuser"

    def test_register_missing_username(self, client):
        response = client.post("/auth/register", data={
            "username": "",
            "password": "password123",
            "password_confirm": "password123",
        }, follow_redirects=True)
        assert response.status_code == 200
        assert "用户名和密码均为必填项" in get_text(response)

    def test_register_missing_password(self, client):
        response = client.post("/auth/register", data={
            "username": "newuser",
            "password": "",
            "password_confirm": "",
        }, follow_redirects=True)
        assert response.status_code == 200
        assert "用户名和密码均为必填项" in get_text(response)

    def test_register_username_too_short(self, client):
        response = client.post("/auth/register", data={
            "username": "ab",
            "password": "password123",
            "password_confirm": "password123",
        }, follow_redirects=True)
        assert response.status_code == 200
        assert "用户名至少需要3个字符" in get_text(response)

    def test_register_password_too_short(self, client):
        response = client.post("/auth/register", data={
            "username": "newuser",
            "password": "1234567",
            "password_confirm": "1234567",
        }, follow_redirects=True)
        assert response.status_code == 200
        assert "密码至少需要8个字符" in get_text(response)

    def test_register_password_no_letter(self, client):
        response = client.post("/auth/register", data={
            "username": "newuser",
            "password": "12345678",
            "password_confirm": "12345678",
        }, follow_redirects=True)
        assert response.status_code == 200
        assert "密码必须包含字母" in get_text(response)

    def test_register_password_no_digit(self, client):
        response = client.post("/auth/register", data={
            "username": "newuser",
            "password": "abcdefgh",
            "password_confirm": "abcdefgh",
        }, follow_redirects=True)
        assert response.status_code == 200
        assert "密码必须包含数字" in get_text(response)

    def test_register_password_mismatch(self, client):
        response = client.post("/auth/register", data={
            "username": "newuser",
            "password": "password123",
            "password_confirm": "password456",
        }, follow_redirects=True)
        assert response.status_code == 200
        assert "两次输入的密码不一致" in get_text(response)

    def test_register_duplicate_username(self, client, app):
        with app.app_context():
            existing_user = User(username="existinguser")
            existing_user.set_password("password123")
            db.session.add(existing_user)
            db.session.commit()

        response = client.post("/auth/register", data={
            "username": "existinguser",
            "password": "password123",
            "password_confirm": "password123",
        }, follow_redirects=True)
        assert response.status_code == 200
        assert "用户名已存在" in get_text(response)

    def test_password_is_hashed(self, app):
        with app.app_context():
            client = app.test_client()
            client.post("/auth/register", data={
                "username": "hashuser",
                "password": "MyPass12",
                "password_confirm": "MyPass12",
            })
            user = User.query.filter_by(username="hashuser").first()
            assert user is not None
            assert user.password_hash != "MyPass12"
            assert user.check_password("MyPass12")
            assert not user.check_password("wrongpassword")


class TestLoginPage:
    """测试登录页面"""

    def test_login_page_loads(self, client):
        response = client.get("/auth/login")
        assert response.status_code == 200
        assert "用户登录" in get_text(response)

    def test_login_page_accessible_when_logged_out(self, client):
        response = client.get("/auth/login")
        assert response.status_code == 200

    def test_login_page_redirect_when_logged_in(self, authenticated_client):
        response = authenticated_client.get("/auth/login", follow_redirects=False)
        assert response.status_code == 302


class TestLoginFunctionality:
    """测试登录功能"""

    def test_login_success(self, client, app):
        with app.app_context():
            user = User(username="loginuser")
            user.set_password("correctpassword1")
            db.session.add(user)
            db.session.commit()

        response = client.post("/auth/login", data={
            "username": "loginuser",
            "password": "correctpassword1",
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_login_wrong_password(self, client, app):
        with app.app_context():
            user = User(username="testuser2")
            user.set_password("correctpassword1")
            db.session.add(user)
            db.session.commit()

        response = client.post("/auth/login", data={
            "username": "testuser2",
            "password": "wrongpassword",
        }, follow_redirects=True)
        assert response.status_code == 200
        assert "用户名或密码错误" in get_text(response)

    def test_login_nonexistent_user(self, client):
        response = client.post("/auth/login", data={
            "username": "nonexistent",
            "password": "somepassword",
        }, follow_redirects=True)
        assert response.status_code == 200
        assert "用户名或密码错误" in get_text(response)

    def test_login_missing_username(self, client):
        response = client.post("/auth/login", data={
            "username": "",
            "password": "somepassword",
        }, follow_redirects=True)
        assert response.status_code == 200
        assert "用户名和密码均为必填项" in get_text(response)

    def test_login_missing_password(self, client):
        response = client.post("/auth/login", data={
            "username": "someuser",
            "password": "",
        }, follow_redirects=True)
        assert response.status_code == 200
        assert "用户名和密码均为必填项" in get_text(response)

    def test_login_inactive_user(self, client, app):
        with app.app_context():
            user = User(username="inactiveuser")
            user.set_password("password123")
            user.is_active = False
            db.session.add(user)
            db.session.commit()

        response = client.post("/auth/login", data={
            "username": "inactiveuser",
            "password": "password123",
        }, follow_redirects=True)
        assert response.status_code == 200
        assert "账户已被禁用" in get_text(response)

    def test_login_updates_last_login(self, client, app):
        with app.app_context():
            user = User(username="timinguser")
            user.set_password("password123")
            db.session.add(user)
            db.session.commit()
            uid = user.id

        client.post("/auth/login", data={
            "username": "timinguser",
            "password": "password123",
        })

        with app.app_context():
            refreshed = User.query.filter_by(username="timinguser").first()
            assert refreshed is not None
            assert refreshed.last_login is not None

    def test_login_remember_me(self, client, app):
        with app.app_context():
            user = User(username="rememberuser")
            user.set_password("password123")
            db.session.add(user)
            db.session.commit()

        response = client.post("/auth/login", data={
            "username": "rememberuser",
            "password": "password123",
            "remember_me": "1",
        }, follow_redirects=True)
        assert response.status_code == 200


class TestLogoutFunctionality:
    """测试退出登录功能"""

    def test_logout_success(self, authenticated_client):
        response = authenticated_client.post("/auth/logout", follow_redirects=False)
        assert response.status_code == 302
        assert "/auth/login" in response.location

        login_page = authenticated_client.get("/auth/login")
        assert login_page.status_code == 200

    def test_logout_requires_login(self, client):
        response = client.post("/auth/logout", follow_redirects=False)
        assert response.status_code == 302


class TestProfileFunctionality:
    """测试个人中心功能"""

    def test_profile_accessible_when_logged_in(self, authenticated_client):
        response = authenticated_client.get("/auth/profile")
        assert response.status_code == 200
        assert "auth_fixture_user" in get_text(response)

    def test_profile_requires_login(self, client):
        response = client.get("/auth/profile", follow_redirects=False)
        assert response.status_code == 302
