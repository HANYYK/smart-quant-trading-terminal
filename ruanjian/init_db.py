"""
数据库初始化脚本
运行方式: python init_db.py [--force]
  --force   删除旧数据库并重新创建所有表（会丢失所有数据）
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from extensions import db


def init_database(force: bool = False):
    app = create_app("development")

    with app.app_context():
        db_path = os.path.join(os.path.dirname(__file__), "quant_trading.db")

        if force:
            if os.path.exists(db_path):
                os.remove(db_path)
                print(f"已删除旧数据库: {db_path}")
        else:
            if os.path.exists(db_path):
                from sqlalchemy import inspect
                inspector = inspect(db.engine)
                existing_tables = inspector.get_table_names()
                if existing_tables:
                    print(f"数据库已存在: {db_path}")
                    print(f"已有表: {existing_tables}")
                    print("如需重建，请加 --force 参数: python init_db.py --force")
                    return

        db.create_all()
        print("数据库表创建成功!")

        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        print(f"已创建的表: {tables}")


if __name__ == "__main__":
    force = "--force" in sys.argv or "-f" in sys.argv
    init_database(force=force)
    if force:
        print("\n数据库已重建，所有数据已丢失！")
    print("\n数据库初始化完成。请重新启动应用。")
