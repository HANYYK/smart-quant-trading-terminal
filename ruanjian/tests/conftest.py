"""
测试配置文件 - pytest fixtures
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from app import create_app
from extensions import db


@pytest.fixture(scope="function")
def app():
    """创建测试应用实例，每个测试函数使用独立的数据库"""
    test_app = create_app("testing")
    test_app.config.update({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SECRET_KEY": "test-secret-key",
    })

    with test_app.app_context():
        db.create_all()
        yield test_app
        db.session.remove()
        db.drop_all()


@pytest.fixture(scope="function")
def client(app):
    """创建测试客户端"""
    return app.test_client()


@pytest.fixture(scope="function")
def runner(app):
    """创建 CLI 测试运行器"""
    return app.test_cli_runner()


@pytest.fixture(scope="function")
def authenticated_client(app):
    """创建一个已认证的测试客户端。"""
    with app.app_context():
        from models import User
        user = User(username="auth_fixture_user")
        user.set_password("testpass123")
        db.session.add(user)
        db.session.commit()

    client = app.test_client()
    client.post("/auth/login", data={
        "username": "auth_fixture_user",
        "password": "testpass123",
    }, follow_redirects=False)
    return client
