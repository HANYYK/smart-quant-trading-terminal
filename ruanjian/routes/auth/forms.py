"""
认证表单 - 使用 Flask-WTF 统一管理
CSRF token 由 WTForms 自动处理
"""
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField
from wtforms.validators import DataRequired, Length, EqualTo, Regexp, Email


class RegisterForm(FlaskForm):
    """用户注册表单"""
    username = StringField(
        "用户名",
        validators=[
            DataRequired(message="用户名和密码均为必填项"),
            Length(min=3, max=30, message="用户名至少需要3个字符"),
            Regexp(
                r"^[a-zA-Z0-9_\u4e00-\u9fff]+$",
                message="用户名只能包含字母、数字、下划线和中文字符",
            ),
        ],
    )
    password = PasswordField(
        "密码",
        validators=[
            DataRequired(message="用户名和密码均为必填项"),
            Length(min=8, max=128, message="密码至少需要8个字符"),
            Regexp(
                r".*[A-Za-z].*",
                message="密码必须包含字母",
            ),
            Regexp(
                r".*\d.*",
                message="密码必须包含数字",
            ),
        ],
    )
    password_confirm = PasswordField(
        "确认密码",
        validators=[
            DataRequired(message="请再次输入密码"),
            EqualTo("password", message="两次输入的密码不一致"),
        ],
    )


class LoginForm(FlaskForm):
    """用户登录表单"""
    username = StringField(
        "用户名/邮箱",
        validators=[DataRequired(message="用户名和密码均为必填项")],
    )
    password = PasswordField(
        "密码",
        validators=[DataRequired(message="用户名和密码均为必填项")],
    )
    remember_me = BooleanField("记住我")


class PasswordResetRequestForm(FlaskForm):
    """密码重置请求表单"""
    email = StringField(
        "邮箱",
        validators=[
            DataRequired(message="邮箱不能为空"),
            Email(message="请输入有效的邮箱地址"),
        ],
    )


class PasswordResetForm(FlaskForm):
    """密码重置表单"""
    password = PasswordField(
        "新密码",
        validators=[
            DataRequired(message="密码不能为空"),
            Length(min=8, max=128, message="密码至少需要8个字符"),
            Regexp(
                r".*[A-Za-z].*",
                message="密码必须包含字母",
            ),
            Regexp(
                r".*\d.*",
                message="密码必须包含数字",
            ),
        ],
    )
    password_confirm = PasswordField(
        "确认密码",
        validators=[
            DataRequired(message="请再次输入密码"),
            EqualTo("password", message="两次输入的密码不一致"),
        ],
    )
