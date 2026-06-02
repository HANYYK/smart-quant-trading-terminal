"""
用户认证路由
- 登录 / 注册 / 登出 / 个人中心
- 限流：同一 IP 5 分钟内最多尝试 5 次
"""
from flask import Blueprint, render_template, redirect, url_for, flash, request, session, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from datetime import datetime, timedelta, timezone
from extensions import db, limiter
from models import User, LoginAttempt
from routes.auth.forms import RegisterForm, LoginForm, PasswordResetRequestForm, PasswordResetForm

auth_bp = Blueprint("auth", __name__)

# 限流配置
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_MINUTES = 10


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """用户注册"""
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    form = RegisterForm()

    if form.validate_on_submit():
        # 检查用户名是否已存在
        existing_user = User.query.filter(
            (User.username == form.username.data) |
            (User.email == form.username.data)
        ).first()
        if existing_user:
            form.username.errors.append("邮箱已被注册" if "@" in form.username.data else "用户名已存在")
            return render_template("auth/register.html", form=form)

        user = User(
            username=form.username.data,
            email=form.username.data if "@" in form.username.data else None
        )
        try:
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()

            login_user(user)
            flash("注册成功！欢迎使用智能量化交易终端", "success")
            return redirect(url_for("dashboard.index"))
        except ValueError as e:
            form.password.errors.append(str(e))
            return render_template("auth/register.html", form=form)
        except Exception:
            db.session.rollback()
            form.username.errors.append("注册失败，请稍后重试")

    return render_template("auth/register.html", form=form)


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def login():
    """用户登录"""
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    client_ip = request.remote_addr or "unknown"

    # 检查是否被锁
    locked, remaining = _check_ip_lockout(client_ip)
    if locked:
        minutes = max(1, remaining // 60 + 1)
        flash(f"登录尝试次数过多，请在 {minutes} 分钟后重试", "danger")
        return render_template("auth/login.html", form=LoginForm())

    form = LoginForm()

    if form.validate_on_submit():
        # 查询用户（支持用户名或邮箱登录）
        user = User.query.filter(
            (User.username == form.username.data) |
            (User.email == form.username.data)
        ).first()

        if user is None or not user.check_password(form.password.data):
            _record_login_attempt(client_ip, form.username.data, False)
            remaining_attempts = MAX_LOGIN_ATTEMPTS - _get_attempt_count(client_ip)

            if remaining_attempts <= 0:
                flash(f"连续 {MAX_LOGIN_ATTEMPTS} 次登录失败，请在 {LOCKOUT_MINUTES} 分钟后重试", "danger")
            else:
                flash(f"用户名或密码错误，剩余尝试次数: {remaining_attempts}", "danger")
            return render_template("auth/login.html", form=form)

        if not user.is_active:
            flash("账户已被禁用，请联系管理员", "danger")
            return render_template("auth/login.html", form=form)

        # 登录成功
        _record_login_attempt(client_ip, user.username, True)
        login_user(user, remember=form.remember_me.data)
        session.permanent = form.remember_me.data

        try:
            user.last_login = datetime.now(timezone.utc)
            db.session.commit()
        except Exception:
            db.session.rollback()

        # next 参数来源验证
        next_page = request.args.get("next")
        if next_page and not next_page.startswith(("http://", "https://", "//")):
            return redirect(next_page)
        return redirect(url_for("dashboard.index"))

    return render_template("auth/login.html", form=form)


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    """用户登出"""
    logout_user()
    flash("已成功退出登录", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/profile")
@login_required
def profile():
    """个人中心"""
    return render_template("auth/profile.html", user=current_user)


@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    """修改密码"""
    from wtforms import PasswordField
    from wtforms.validators import DataRequired, Length, EqualTo
    from flask_wtf import FlaskForm

    class ChangePasswordForm(FlaskForm):
        old_password = PasswordField("当前密码", validators=[DataRequired()])
        new_password = PasswordField("新密码", validators=[
            DataRequired(),
            Length(min=8, max=128),
        ])
        confirm_password = PasswordField("确认密码", validators=[
            DataRequired(),
            EqualTo("new_password", message="两次密码不一致")
        ])

    form = ChangePasswordForm()

    if form.validate_on_submit():
        if not current_user.check_password(form.old_password.data):
            flash("当前密码错误", "danger")
            return render_template("auth/change_password.html", form=form)

        try:
            current_user.set_password(form.new_password.data)
            db.session.commit()
            flash("密码修改成功", "success")
            return redirect(url_for("auth.profile"))
        except ValueError as e:
            form.new_password.errors.append(str(e))
        except Exception:
            db.session.rollback()
            flash("密码修改失败，请稍后重试", "danger")

    return render_template("auth/change_password.html", form=form)


@auth_bp.route("/edit-profile", methods=["GET", "POST"])
@login_required
def edit_profile():
    """编辑个人资料"""
    from flask_wtf import FlaskForm
    from wtforms import StringField
    from wtforms.validators import DataRequired, Length

    class EditProfileForm(FlaskForm):
        username = StringField("用户名", validators=[DataRequired(), Length(min=3, max=80)])

    form = EditProfileForm(obj=current_user)

    if form.validate_on_submit():
        current_user.username = form.username.data
        try:
            db.session.commit()
            flash("个人资料已更新", "success")
            return redirect(url_for("auth.profile"))
        except Exception:
            db.session.rollback()
            flash("更新失败，用户名可能已被占用", "danger")

    return render_template("auth/edit_profile.html", form=form)


# ============ 内部函数 ============

def _check_ip_lockout(client_ip: str) -> tuple[bool, int]:
    """检查IP是否被锁定（使用 SQL 聚合代替全量加载）"""
    from datetime import timedelta
    from sqlalchemy import func
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=LOCKOUT_MINUTES)

    failed_count = db.session.query(func.count(LoginAttempt.id)).filter(
        LoginAttempt.ip_address == client_ip,
        LoginAttempt.attempted_at > cutoff,
        LoginAttempt.success == False
    ).scalar() or 0

    if failed_count >= MAX_LOGIN_ATTEMPTS:
        oldest = LoginAttempt.query.filter(
            LoginAttempt.ip_address == client_ip,
            LoginAttempt.attempted_at > cutoff,
            LoginAttempt.success == False
        ).order_by(LoginAttempt.attempted_at.asc()).first()

        if oldest:
            lockout_end = oldest.attempted_at + timedelta(minutes=LOCKOUT_MINUTES)
            remaining = int((lockout_end - datetime.now(timezone.utc)).total_seconds())
            if remaining > 0:
                return True, remaining

    return False, 0


def _get_attempt_count(client_ip: str) -> int:
    """获取失败尝试次数（SQL 计数）"""
    from datetime import timedelta
    from sqlalchemy import func
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=LOCKOUT_MINUTES)

    return db.session.query(func.count(LoginAttempt.id)).filter(
        LoginAttempt.ip_address == client_ip,
        LoginAttempt.attempted_at > cutoff,
        LoginAttempt.success == False
    ).count()


def _record_login_attempt(ip_address: str, username: str, success: bool) -> None:
    """记录登录尝试"""
    attempt = LoginAttempt(
        ip_address=ip_address,
        username=username,
        success=success
    )
    db.session.add(attempt)
    db.session.commit()

