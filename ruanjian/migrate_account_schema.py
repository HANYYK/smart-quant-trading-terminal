"""
Standalone SQLite migration for simulated account tables.

Run with:
    python migrate_account_schema.py
"""
from __future__ import annotations

import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATABASES = [
    BASE_DIR / "instance" / "quant_trading.db",
    BASE_DIR.parent / "instance" / "quant_trading.db",
]


def add_column(cursor: sqlite3.Cursor, table: str, column: str, definition: str) -> bool:
    columns = {row[1] for row in cursor.execute(f"PRAGMA table_info({table})")}
    if not columns or column in columns:
        return False
    cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    return True


def migrate_database(path: Path) -> None:
    if not path.exists():
        print(f"skip missing database: {path}")
        return

    with sqlite3.connect(path) as conn:
        cursor = conn.cursor()
        changed = []

        if add_column(cursor, "fund_trades", "trade_type", "VARCHAR(20)"):
            cursor.execute("UPDATE fund_trades SET trade_type = 'direct' WHERE trade_type IS NULL")
            changed.append("fund_trades.trade_type")
        if add_column(cursor, "fund_trades", "profit", "FLOAT"):
            changed.append("fund_trades.profit")
        if add_column(cursor, "trades", "profit", "FLOAT"):
            changed.append("trades.profit")
        if add_column(cursor, "fund_positions", "total_invested", "FLOAT NOT NULL DEFAULT 0.0"):
            changed.append("fund_positions.total_invested")

        conn.commit()

    if changed:
        print(f"updated {path}: {', '.join(changed)}")
    else:
        print(f"ok {path}: no schema changes needed")


def main() -> None:
    for database in DATABASES:
        migrate_database(database)


if __name__ == "__main__":
    main()
