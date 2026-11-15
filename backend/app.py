"""paKento backend — Canteen Credit Book (Flask).

Students hand money to the canteen; the canteen holds it for them.
When they buy, the amount is subtracted. Cleared credit is archived to History.

Storage: SQLite (default) or MySQL — see backend/database.py.

Run:  ./venv/bin/python backend/app.py
"""
import os
import sqlite3
from datetime import datetime, timezone
from functools import wraps

from flask import Flask, g, jsonify, request, send_from_directory, session
from flask_cors import CORS

import database

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

app = Flask(
    __name__,
    static_folder=os.path.join(BASE, "frontend"),
    static_url_path="",
)
app.secret_key = os.environ.get("PAKENTO_SECRET", "change-me-in-production")
CORS(app)  # allow frontend on Vercel to call backend


# ---------------- Database ----------------
def db():
    if "db" not in g:
        g.db = database.connect()
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_db():
    database.init_db()


# ---------------- Password hashing ----------------
import hashlib
import hmac


def hash_password(password: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode(), b"pakento-static-salt", 100_000
    ).hex()


def check_password(password: str, stored: str) -> bool:
    return hmac.compare_digest(hash_password(password), stored)


# ---------------- Token store (mobile preview can't use cookies) ----------------
TOKENS = {}  # token -> username


def user_from_request():
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        username = TOKENS.get(auth[7:])
        if username:
            return username
    return session.get("username")


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not user_from_request():
            return jsonify(error="Not logged in"), 401
        return fn(*args, **kwargs)
    return wrapper


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def debt_left(conn, debt_id):
    row = conn.execute(
        """SELECT d.amount - COALESCE((SELECT SUM(amount) FROM payments WHERE debt_id = d.id), 0)
           AS remaining FROM debts d WHERE d.id = ?""",
        (debt_id,),
    ).fetchone()
    return row["remaining"]


# ---------------- Static frontend ----------------
@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


# ---------------- Auth ----------------
@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    row = db().execute(
        "SELECT * FROM staff WHERE username = ?", (data.get("username", ""),)
    ).fetchone()
    if not row or not check_password(data.get("password", ""), row["password_hash"]):
        return jsonify(error="Wrong username or password"), 401
    import secrets
    token = secrets.token_hex(24)
    TOKENS[token] = row["username"]
    session["username"] = row["username"]
    session["role"] = row["role"]
    return jsonify(user={"username": row["username"], "role": row["role"]}, token=token)


@app.route("/api/logout", methods=["POST"])
def logout():
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        TOKENS.pop(auth[7:], None)
    session.clear()
    return jsonify(ok=True)


@app.route("/api/change-password", methods=["POST"])
@login_required
def change_password():
    data = request.get_json() or {}
    old, new = data.get("old", ""), data.get("new", "")
    if len(new) < 6:
        return jsonify(error="New password must be at least 6 characters"), 400
    conn = db()
    row = conn.execute(
        "SELECT password_hash FROM staff WHERE username = ?", (user_from_request(),)
    ).fetchone()
    if not check_password(old, row["password_hash"]):
        return jsonify(error="Current password is wrong"), 401
    conn.execute(
        "UPDATE staff SET password_hash = ? WHERE username = ?",
        (hash_password(new), user_from_request()),
    )
    conn.commit()
    return jsonify(ok=True)


# ---------------- Students & debts ----------------
def students_query(date_filter=None):
    """List all students with outstanding debt total + red marks."""
    conn = db()
    sql = """
        SELECT s.id, s.name, s.class, s.created_at,
               COALESCE(SUM(CASE WHEN d.status != 'paid' THEN d.amount END), 0) AS original_total,
               COALESCE(SUM(
                   CASE WHEN d.status != 'paid'
                   THEN d.amount - COALESCE((SELECT SUM(amount) FROM payments p WHERE p.debt_id = d.id), 0)
                   END), 0) AS owes
        FROM students s
        LEFT JOIN debts d ON d.student_id = s.id AND d.archived = 0
    """
    params = []
    if date_filter:
        sql += " AND date(d.created_at) = ? "
        params.append(date_filter)
    sql += " GROUP BY s.id ORDER BY owes DESC, s.name"
    return conn.execute(sql, params).fetchall()


@app.route("/api/students", methods=["GET"])
@login_required
def list_students():
    return jsonify(students_query(request.args.get("date")))


@app.route("/api/students/<int:sid>", methods=["GET"])
@login_required
def student_detail(sid):
    conn = db()
    s = conn.execute("SELECT * FROM students WHERE id=?", (sid,)).fetchone()
    if not s:
        return jsonify(error="Student not found"), 404
    debts = conn.execute(
        """SELECT d.id, d.amount, d.item, d.status, d.recorded_by, d.created_at,
                  COALESCE((SELECT SUM(amount) FROM payments p WHERE p.debt_id = d.id), 0) AS paid
           FROM debts d WHERE d.student_id = ? AND d.archived = 0 ORDER BY d.id DESC LIMIT 100""",
        (sid,),
    ).fetchall()
    history = []
    for d in debts:
        history.append({"kind": "debt", "id": d["id"], "amount": d["amount"],
                        "item": d["item"], "status": d["status"],
                        "by": d["recorded_by"], "created_at": d["created_at"]})
    pays = conn.execute(
        """SELECT p.id, p.debt_id, p.amount, p.paid_by, p.created_at
           FROM payments p JOIN debts d ON d.id = p.debt_id
           WHERE d.student_id = ? ORDER BY p.id DESC LIMIT 100""",
        (sid,),
    ).fetchall()
    for p in pays:
        history.append({"kind": "payment", "id": p["id"], "amount": p["amount"],
                        "by": p["paid_by"], "created_at": p["created_at"]})
    history.sort(key=lambda h: h["created_at"], reverse=True)
    owes = sum(d["amount"] - d["paid"] for d in debts if d["status"] != "paid")
    return jsonify(id=s["id"], name=s["name"], **{"class": s["class"]},
                   student_no=f"S-{s['id']:04d}", owes=owes, history=history)


def get_or_create_student(conn, name, klass):
    name, klass = name.strip(), klass.strip()
    row = conn.execute(
        "SELECT id FROM students WHERE LOWER(name)=LOWER(?) AND LOWER(class)=LOWER(?)",
        (name, klass),
    ).fetchone()
    if row:
        return row["id"], False
    sql = "INSERT INTO students (name, class, created_at) VALUES (?,?,?)"
    conn.execute(sql, (name, klass, now()))
    if conn.engine == "postgres":
        r = conn.execute("SELECT id FROM students WHERE name=? AND class=?",
                         (name, klass)).fetchone()
        return r["id"], True
    return conn.lastrowid, True


# ---------------- Record a debt ----------------
@app.route("/api/debts", methods=["POST"])
@login_required
def add_debt():
    """Staff records money a student handed to the canteen."""
    data = request.get_json() or {}
    name, klass = (data.get("name") or ""), (data.get("class") or "")
    amount = data.get("amount")
    if not name.strip() or not klass.strip():
        return jsonify(error="Name and class are required"), 400
    if not isinstance(amount, int) or amount <= 0:
        return jsonify(error="Amount must be a positive number"), 400

    recorded_by = user_from_request()
    conn = db()
    sid, _new = get_or_create_student(conn, name, klass)
    conn.execute(
        "INSERT INTO debts (student_id, amount, item, recorded_by, status, created_at)"
        " VALUES (?,?,?,?, 'unpaid', ?)",
        (sid, amount, "", recorded_by, now()),
    )
    conn.commit()
    return jsonify(ok=True, student_id=sid), 201

# ---------------- Edit student (name / class) ----------------
@app.route("/api/students/<int:sid>", methods=["PATCH"])
@login_required
def edit_student(sid):
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    klass = (data.get("class") or "").strip()
    if not name or not klass:
        return jsonify(error="Name and class are required"), 400
    conn = db()
    if not conn.execute("SELECT 1 FROM students WHERE id=?", (sid,)).fetchone():
        return jsonify(error="Student not found"), 404
    # If another student already has that name+class, merge into it
    other = conn.execute(
        "SELECT id FROM students WHERE LOWER(name)=LOWER(?) AND LOWER(class)=LOWER(?) AND id != ?",
        (name, klass, sid),
    ).fetchone()
    if other:
        conn.execute("UPDATE debts SET student_id=? WHERE student_id=?", (other["id"], sid))
        conn.execute("DELETE FROM students WHERE id=?", (sid,))
        conn.commit()
        return jsonify(ok=True, merged_into=other["id"])
    conn.execute("UPDATE students SET name=?, class=? WHERE id=?", (name, klass, sid))
    conn.commit()
    return jsonify(ok=True)


# ---------------- Adjust money: ➕ add debt / ➖ remove (pay) ----------------
@app.route("/api/adjust", methods=["POST"])
@login_required
def adjust():
    """plus → student gave more money (credit in). minus → student used money (bought)."""
    data = request.get_json() or {}
    sid, op, amount = data.get("student_id"), data.get("op"), data.get("amount")
    if op not in ("plus", "minus"):
        return jsonify(error="op must be 'plus' or 'minus'"), 400
    if not isinstance(amount, int) or amount <= 0:
        return jsonify(error="Amount must be a positive number"), 400

    conn = db()
    if not conn.execute("SELECT 1 FROM students WHERE id=?", (sid,)).fetchone():
        return jsonify(error="Student not found"), 404

    if op == "plus":
        conn.execute(
            "INSERT INTO debts (student_id, amount, item, recorded_by, status, created_at)"
            " VALUES (?,?, '', ?, 'unpaid', ?)",
            (sid, amount, user_from_request(), now()),
        )
        conn.commit()
        return jsonify(ok=True, direction="added", amount=amount)

    # minus: subtract from open debts, oldest first
    open_debts = conn.execute(
        """SELECT id, amount,
                  amount - COALESCE((SELECT SUM(p.amount) FROM payments p WHERE p.debt_id = d.id), 0) AS remaining
           FROM debts d WHERE student_id = ? AND status != 'paid' AND archived = 0 ORDER BY id""",
        (sid,),
    ).fetchall()
    total_owed = sum(d["remaining"] for d in open_debts)
    if amount > total_owed:
        return jsonify(error=f"Student only has {total_owed} RWF left — can't use {amount}"), 400

    left = amount
    for d in open_debts:
        if left == 0:
            break
        take = min(left, d["remaining"])
        conn.execute(
            "INSERT INTO payments (debt_id, amount, paid_by, created_at) VALUES (?,?,?,?)",
            (d["id"], take, user_from_request(), now()),
        )
        status = "paid" if d["remaining"] - take == 0 else "partial"
        conn.execute("UPDATE debts SET status=? WHERE id=?", (status, d["id"]))
        left -= take
    conn.commit()
    return jsonify(ok=True, direction="removed", amount=amount)


# ---------------- Pay a debt (subtraction part) ----------------
@app.route("/api/pay", methods=["POST"])
@login_required
def pay():
    """Subtract money from a debt. When nothing remains → marked PAID."""
    data = request.get_json() or {}
    debt_id, amount = data.get("debt_id"), data.get("amount")
    if not isinstance(amount, int) or amount <= 0:
        return jsonify(error="Amount must be a positive number"), 400

    conn = db()
    debt = conn.execute("SELECT * FROM debts WHERE id=?", (debt_id,)).fetchone()
    if not debt:
        return jsonify(error="Debt not found"), 404
    remaining = debt_left(conn, debt_id)
    if remaining == 0:
        return jsonify(error="This debt is already paid"), 400
    if amount > remaining:
        return jsonify(error=f"Debt is only {remaining} RWF — pay less"), 400

    paid_by = user_from_request()
    conn.execute(
        "INSERT INTO payments (debt_id, amount, paid_by, created_at) VALUES (?,?,?,?)",
        (debt_id, amount, paid_by, now()),
    )
    status = "paid" if remaining - amount == 0 else "partial"
    conn.execute("UPDATE debts SET status=? WHERE id=?", (status, debt_id))
    conn.commit()
    return jsonify(ok=True, remaining=remaining - amount,
                   paid=status == "paid"), 201


# ---------------- Daily ledger / timetable ----------------
@app.route("/api/day", methods=["GET"])
@login_required
def day_ledger():
    """All debt entries of a given date, with red/paid marks."""
    date = request.args.get("date") or today()
    conn = db()
    rows = conn.execute(
        """SELECT d.id, d.amount, d.item, d.status, d.recorded_by, d.created_at,
                  s.name, s.class,
                  d.amount - COALESCE((SELECT SUM(amount) FROM payments p WHERE p.debt_id=d.id),0) AS remaining
           FROM debts d JOIN students s ON s.id = d.student_id
           WHERE date(d.created_at) = ? AND d.archived = 0
           ORDER BY d.id DESC""",
        (date,),
    ).fetchall()
    total_unpaid = sum(r["remaining"] for r in rows)
    return jsonify(date=date, entries=rows,
                   total_unpaid=total_unpaid)


@app.route("/api/calendar", methods=["GET"])
@login_required
def calendar_marks():
    """Red marks per day for a month (YYYY-MM)."""
    month = request.args.get("month") or datetime.now(timezone.utc).strftime("%Y-%m")
    conn = db()
    rows = conn.execute(
        """SELECT date(created_at) AS day,
                  COUNT(*) AS debts,
                  SUM(CASE status WHEN 'unpaid' THEN 1 ELSE 0 END) AS unpaid,
                  COALESCE(SUM(CASE status WHEN 'unpaid' THEN amount ELSE 0 END),0) AS unpaid_amount
           FROM debts WHERE substr(created_at, 1, 7) = ? AND archived = 0
           GROUP BY day ORDER BY day""",
        (month,),
    ).fetchall()
    return jsonify(month=month, days=rows)


# ---------------- Clear used-up credit (archive) ----------------
@app.route("/api/archive", methods=["POST"])
@login_required
def archive():
    """Archive fully used-up credit of selected students → moves it to History."""
    data = request.get_json() or {}
    ids = data.get("student_ids")
    if not isinstance(ids, list) or not ids:
        return jsonify(error="Select at least one student"), 400
    conn = db()
    q = ", ".join(["?"] * len(ids))
    if conn.engine in ("mysql", "postgres"):
        q = q.replace("?", "%s")
    cur = conn.execute(
        f"""UPDATE debts SET archived = 1
            WHERE student_id IN ({q}) AND status = 'paid' AND archived = 0""",
        ids,
    )
    conn.commit()
    return jsonify(ok=True, archived=cur.rowcount)


@app.route("/api/history", methods=["GET"])
@login_required
def history():
    """Everything cleared (used up) + the payments that cleared it."""
    conn = db()
    rows = conn.execute(
        """SELECT d.id, s.name, s.class, d.amount, d.recorded_by, d.created_at,
                  COALESCE((SELECT SUM(amount) FROM payments p WHERE p.debt_id = d.id), 0) AS paid,
                  (SELECT MAX(created_at) FROM payments p WHERE p.debt_id = d.id) AS cleared_at
           FROM debts d JOIN students s ON s.id = d.student_id
           WHERE d.archived = 1 ORDER BY d.created_at DESC LIMIT 300"""
    ).fetchall()
    total = conn.execute(
        "SELECT COALESCE(SUM(amount),0) AS total FROM debts WHERE archived = 1"
    ).fetchone()["total"]
    return jsonify(total=total, entries=rows)


# ---------------- Stats ----------------
@app.route("/api/stats", methods=["GET"])
@login_required
def stats():
    conn = db()
    total_debtors = conn.execute(
        """SELECT COUNT(DISTINCT student_id) AS n FROM debts WHERE status='unpaid' AND archived = 0"""
    ).fetchone()["n"]
    total_owed = conn.execute(
        """SELECT COALESCE(SUM(d.amount - COALESCE((SELECT SUM(amount) FROM payments p WHERE p.debt_id=d.id),0)),0) AS n
           FROM debts d WHERE d.status='unpaid' AND d.archived = 0"""
    ).fetchone()["n"]
    paid_today = conn.execute(
        """SELECT COALESCE(SUM(amount),0) AS n FROM payments WHERE date(created_at)=?""",
        (today(),),
    ).fetchone()["n"]
    debts_today = conn.execute(
        "SELECT COALESCE(SUM(amount),0) AS n FROM debts WHERE date(created_at)=?",
        (today(),),
    ).fetchone()["n"]
    return jsonify(debtors=total_debtors, total_owed=total_owed,
                   paid_today=paid_today, debts_today=debts_today)


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
