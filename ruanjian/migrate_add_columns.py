"""
数据库迁移脚本 - 添加缺失的列
运行方式: python migrate_add_columns.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from extensions import db
from sqlalchemy import inspect, text


def find_database_path():
    """查找数据库文件位置"""
    possible_paths = [
        os.path.join(os.path.dirname(__file__), "quant_trading.db"),
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "quant_trading.db"),
        os.path.join(os.getcwd(), "quant_trading.db"),
    ]
    for path in possible_paths:
        if os.path.exists(path):
            return path
    return possible_paths[0]  # 返回第一个作为默认值


def migrate():
    app = create_app("development")

    with app.app_context():
        # 使用 SQLAlchemy 的 engine 来检查数据库
        inspector = inspect(db.engine)

        # 获取数据库中的表
        existing_tables = db.engine.table_names() if hasattr(db.engine, 'table_names') else inspector.get_table_names()

        if not existing_tables:
            print("数据库中没有表，请先运行应用来创建数据库")
            return

        print(f"数据库已有表: {existing_tables}")

        inspector = inspect(db.engine)
        existing_columns = [col['name'] for col in inspector.get_columns('users')]
        print(f"当前 users 表的列: {existing_columns}")

        # 缺失的列
        missing_columns = {
            'email_verified': 'BOOLEAN DEFAULT 0',
            'email_verification_token': 'VARCHAR(64)',
            'password_reset_token': 'VARCHAR(64)',
            'password_reset_expires': 'DATETIME',
        }

        added = []
        for col_name, col_type in missing_columns.items():
            if col_name not in existing_columns:
                try:
                    sql = f"ALTER TABLE users ADD COLUMN {col_name} {col_type}"
                    db.session.execute(text(sql))
                    db.session.commit()
                    added.append(col_name)
                    print(f"✓ 已添加列: {col_name}")
                except Exception as e:
                    print(f"✗ 添加列 {col_name} 失败: {e}")
                    db.session.rollback()
            else:
                print(f"- 列已存在: {col_name}")

        if added:
            print(f"\n迁移完成! 已添加 {len(added)} 个列: {added}")
        else:
            print("\n无需迁移，所有列已存在。")


if __name__ == "__main__":
    migrate()
