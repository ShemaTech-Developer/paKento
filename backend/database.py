"""paKento database layer.

Engines (switch with environment variables):
  - sqlite  (default): zero setup, single file, perfect for one device
  - mysql                 : MySQL / MariaDB, for the cafeteria server
  - postgres               : PostgreSQL (Supabase), hosted free-tier DB

Switch:
  PAKENTO_DB=sqlite
  PAKENTO_DB=mysql PAKENTO_MYSQL_HOST=localhost PAKENTO_MYSQL_USER=root \
              PAKENTO_MYSQL_PASSWORD=secret PAKENTO_MYSQL_NAME=pakento
  PAKENTO_DB=postgres PAKENTO_POSTGRES_DSN=postgres://user:pass@host:5432/dbname
"""
import os
import sqlite3
from decimal import Decimal

ENGINE = os.environ.get("PAKENTO_DB", "sqlite").lower()

SQLITE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pakento.db")

MYSQL = {
    "host": os.environ.get("PAKENTO_MYSQL_HOST", "localhost"),
    "port": int(os.environ.get("PAKENTO_MYSQL_PORT", "3306")),
    "user": os.environ.get("PAKENTO_MYSQL_USER", "root"),
    "password": os.environ.get("PAKENTO_MYSQL_PASSWORD", ""),
    "database": os.environ.get("PAKENTO_MYSQL_NAME", "pakento"),
}

POSTGRES_DSN = os.environ.get("PAKENTO_POSTGRES_DSN", "")


def _clean(v):
    """DBs return DECIMAL for SUM/COUNT — convert to JSON-friendly numbers."""
    if isinstance(v, Decimal):
        i = int(v)
        return i if v == i else float(v)
    return v


class Conn:
    """Thin wrapper: same API for sqlite3 / pymysql / psycopg2."""

    def __init__(self, raw, engine):
        self.raw = raw
        self.engine = engine

    def execute(self, sql, params=()):
        if self.engine in ("mysql", "postgres"):
            sql = sql.replace("?", "%s")
        self.cur = self.raw.cursor()
        self.cur.execute(sql, params)
        return self  # allow chaining .fetchone() / .fetchall() on the wrapper

    @property
    def lastrowid(self):
        return getattr(self.cur, "lastrowid", None)

    def fetchone(self):
        row = self.cur.fetchone()
        if row is None:
            return None
        if self.engine == "sqlite":
            return {k: _clean(v) for k, v in dict(row).items()}
        cols = [d[0] for d in self.cur.description]
        return {k: _clean(v) for k, v in zip(cols, row)}

    def fetchall(self):
        rows = self.cur.fetchall()
        if self.engine == "sqlite":
            return [{k: _clean(v) for k, v in dict(r).items()} for r in rows]
        cols = [d[0] for d in self.cur.description]
        return [{k: _clean(v) for k, v in zip(cols, r)} for r in rows]

    def commit(self):
        self.raw.commit()

    def close(self):
        self.raw.close()


def connect():
    if ENGINE == "mysql":
        import pymysql
        raw = pymysql.connect(
            host=MYSQL["host"], port=MYSQL["port"], user=MYSQL["user"],
            password=MYSQL["password"], database=MYSQL["database"],
            charset="utf8mb4", autocommit=False,
        )
    elif ENGINE == "postgres":
        import psycopg2
        raw = psycopg2.connect(dsn=POSTGRES_DSN, autocommit=False)
    else:
        raw = sqlite3.connect(SQLITE_FILE)
        raw.row_factory = sqlite3.Row
    return Conn(raw, ENGINE)


def engine_name():
    return ENGINE


def _table_exists(conn, table):
    if ENGINE == "postgres":
        cur = conn.execute(
            "SELECT COUNT(*) AS c FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = %s", (table,))
        row = cur.fetchone()
        return bool(row and row["c"])
    if ENGINE == "mysql":
        cur = conn.execute(
            "SELECT COUNT(*) AS c FROM information_schema.tables "
            "WHERE table_schema = DATABASE() AND table_name = %s", (table,))
        row = cur.fetchone()
        return bool(row and row["c"])
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                      (table,))
    rows = cur.fetchall()
    return len(rows) > 0


def init_db():
    conn = connect()

    def create_all():
        if ENGINE == "mysql":
            for sql in [
                """CREATE TABLE IF NOT EXISTS staff (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    username VARCHAR(255) UNIQUE NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    role VARCHAR(50) NOT NULL DEFAULT 'staff')""",
                """CREATE TABLE IF NOT EXISTS students (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    name VARCHAR(255) NOT NULL,
                    class VARCHAR(255) NOT NULL,
                    created_at VARCHAR(50) NOT NULL,
                    UNIQUE(name, class))""",
                """CREATE TABLE IF NOT EXISTS debts (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    student_id INT NOT NULL,
                    amount INT NOT NULL,
                    item VARCHAR(255) DEFAULT '',
                    recorded_by VARCHAR(255) NOT NULL,
                    status VARCHAR(50) NOT NULL DEFAULT 'unpaid',
                    created_at VARCHAR(50) NOT NULL,
                    archived INT NOT NULL DEFAULT 0)""",
                """CREATE TABLE IF NOT EXISTS payments (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    debt_id INT NOT NULL,
                    amount INT NOT NULL,
                    paid_by VARCHAR(255) NOT NULL,
                    created_at VARCHAR(50) NOT NULL)""",
            ]:
                conn.execute(sql)
        elif ENGINE == "postgres":
            for sql in [
                """CREATE TABLE IF NOT EXISTS staff (
                    id SERIAL PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'staff')""",
                """CREATE TABLE IF NOT EXISTS students (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    class TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(name, class))""",
                """CREATE TABLE IF NOT EXISTS debts (
                    id SERIAL PRIMARY KEY,
                    student_id INT NOT NULL,
                    amount INT NOT NULL,
                    item TEXT DEFAULT '',
                    recorded_by TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'unpaid',
                    created_at TEXT NOT NULL,
                    archived INT NOT NULL DEFAULT 0)""",
                """CREATE TABLE IF NOT EXISTS payments (
                    id SERIAL PRIMARY KEY,
                    debt_id INT NOT NULL,
                    amount INT NOT NULL,
                    paid_by TEXT NOT NULL,
                    created_at TEXT NOT NULL)""",
            ]:
                conn.execute(sql)
        else:  # sqlite
            for sql in [
                """CREATE TABLE IF NOT EXISTS staff (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'staff')""",
                """CREATE TABLE IF NOT EXISTS students (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    class TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(name, class))""",
                """CREATE TABLE IF NOT EXISTS debts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id INTEGER NOT NULL,
                    amount INTEGER NOT NULL,
                    item TEXT DEFAULT '',
                    recorded_by TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'unpaid',
                    created_at TEXT NOT NULL,
                    archived INTEGER NOT NULL DEFAULT 0)""",
                """CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    debt_id INTEGER NOT NULL,
                    amount INTEGER NOT NULL,
                    paid_by TEXT NOT NULL,
                    created_at TEXT NOT NULL)""",
            ]:
                conn.execute(sql)
            cols = [r["name"] for r in conn.execute("PRAGMA table_info(debts)").fetchall()]
            if "archived" not in cols:
                conn.execute("ALTER TABLE debts ADD COLUMN archived INTEGER NOT NULL DEFAULT 0")

        conn.commit()

    if ENGINE == "postgres":
        create_all()
    elif ENGINE == "mysql":
        create_all()
        conn.execute("SELECT 1")
        conn.execute("SELECT 1")
        conn.commit()
    else:
        create_all()

    # Default admin account
    import hashlib
    salt = b"pakento-static-salt"
    pw_hash = hashlib.pbkdf2_hmac("sha256", "kento123".encode(), salt, 100_000).hex()
    if not conn.execute("SELECT id FROM staff WHERE username='admin'").fetchone():
        conn.execute("INSERT INTO staff (username, password_hash, role) VALUES (?,?,?)",
                     ("admin", pw_hash, "admin"))
        conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
