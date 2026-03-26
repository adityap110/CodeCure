from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import sqlite3
import os
from datetime import datetime, date

app = Flask(__name__)
app.secret_key = "codecure_secret_2025"

DB_PATH = "codecure.db"

# ─── DB HELPERS ───────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS medicines (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        category TEXT,
        quantity INTEGER DEFAULT 0,
        min_stock INTEGER DEFAULT 10,
        expiry_date TEXT,
        supplier TEXT,
        price REAL DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now'))
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS activity (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        action TEXT,
        detail TEXT,
        user TEXT,
        timestamp TEXT DEFAULT (datetime('now'))
    )""")

    # Seed demo data if empty
    c.execute("SELECT COUNT(*) FROM medicines")
    if c.fetchone()[0] == 0:
        demo = [
            ("Paracetamol 500mg", "Analgesic", 150, 20, "2025-12-01", "MedCo", 2.50),
            ("Amoxicillin 250mg", "Antibiotic", 8, 15, "2025-09-15", "PharmEx", 12.00),
            ("Pantoprazole 40mg", "Antacid", 60, 10, "2026-03-20", "HealthPlus", 5.75),
            ("Cetirizine 10mg",   "Antihistamine", 3, 10, "2024-06-01", "MedCo", 3.00),
            ("Metformin 500mg",   "Antidiabetic", 200, 30, "2026-01-10", "DiaCare", 1.80),
            ("Atorvastatin 10mg", "Statin", 45, 20, "2026-07-22", "CardioMed", 8.50),
            ("Vitamin C 500mg",   "Vitamin", 12, 25, "2025-11-30", "NutriLife", 4.00),
            ("Ibuprofen 400mg",   "Analgesic", 90, 15, "2026-02-14", "PharmEx", 3.25),
        ]
        c.executemany(
            "INSERT INTO medicines (name,category,quantity,min_stock,expiry_date,supplier,price) VALUES (?,?,?,?,?,?,?)",
            demo
        )
        c.execute("INSERT INTO activity (action,detail,user) VALUES (?,?,?)",
                  ("System Init", "Demo data loaded", "system"))

    conn.commit()
    conn.close()

def log_activity(action, detail, user="system"):
    conn = get_db()
    conn.execute("INSERT INTO activity (action,detail,user) VALUES (?,?,?)", (action, detail, user))
    conn.commit()
    conn.close()

# ─── AUTH ──────────────────────────────────────────────────────────────────────

USERS = {
    "admin":      {"password": "1234", "role": "Admin"},
    "pharmacist": {"password": "1234", "role": "Pharmacist"},
    "doctor":     {"password": "1234", "role": "Doctor"},
}

@app.route("/", methods=["GET", "POST"])
def login():
    if "user" in session:
        return redirect(url_for("dashboard"))
    error = None
    if request.method == "POST":
        u = request.form.get("username", "").strip().lower()
        p = request.form.get("password", "").strip()
        if u in USERS and USERS[u]["password"] == p:
            session["user"] = u
            session["role"] = USERS[u]["role"]
            log_activity("Login", f"{u} logged in", u)
            return redirect(url_for("dashboard"))
        error = "Invalid credentials"
    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    user = session.pop("user", "unknown")
    session.pop("role", None)
    log_activity("Logout", f"{user} logged out", user)
    return redirect(url_for("login"))

@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect(url_for("login"))
    return render_template("index.html", user=session["user"], role=session["role"])

# ─── API ───────────────────────────────────────────────────────────────────────

@app.route("/api/stats")
def api_stats():
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    conn = get_db()
    today = date.today().isoformat()
    soon  = "2025-09-30"  # within ~6 months from demo date

    total   = conn.execute("SELECT COUNT(*) FROM medicines").fetchone()[0]
    ok      = conn.execute("SELECT COUNT(*) FROM medicines WHERE quantity >= min_stock AND (expiry_date IS NULL OR expiry_date > ?)", (today,)).fetchone()[0]
    low     = conn.execute("SELECT COUNT(*) FROM medicines WHERE quantity < min_stock AND (expiry_date IS NULL OR expiry_date > ?)", (today,)).fetchone()[0]
    expired = conn.execute("SELECT COUNT(*) FROM medicines WHERE expiry_date <= ?", (today,)).fetchone()[0]
    conn.close()
    return jsonify({"total": total, "ok": ok, "low": low, "expired": expired})

@app.route("/api/medicines", methods=["GET"])
def api_medicines():
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    filter_type = request.args.get("filter", "all")
    today = date.today().isoformat()

    conn = get_db()
    if filter_type == "low":
        rows = conn.execute("SELECT * FROM medicines WHERE quantity < min_stock ORDER BY quantity ASC").fetchall()
    elif filter_type == "expiring":
        rows = conn.execute("SELECT * FROM medicines WHERE expiry_date BETWEEN ? AND '2025-12-31' ORDER BY expiry_date ASC", (today,)).fetchall()
    elif filter_type == "expired":
        rows = conn.execute("SELECT * FROM medicines WHERE expiry_date <= ? ORDER BY expiry_date ASC", (today,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM medicines ORDER BY name ASC").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/medicines", methods=["POST"])
def api_add_medicine():
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    if session["role"] not in ("Admin", "Pharmacist"):
        return jsonify({"error": "Permission denied"}), 403
    data = request.json
    conn = get_db()
    conn.execute(
        "INSERT INTO medicines (name,category,quantity,min_stock,expiry_date,supplier,price) VALUES (?,?,?,?,?,?,?)",
        (data["name"], data.get("category",""), int(data.get("quantity",0)),
         int(data.get("min_stock",10)), data.get("expiry_date",""),
         data.get("supplier",""), float(data.get("price",0)))
    )
    conn.commit()
    conn.close()
    log_activity("Add Medicine", data["name"], session["user"])
    return jsonify({"success": True})

@app.route("/api/medicines/<int:mid>", methods=["PUT"])
def api_update_medicine(mid):
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    if session["role"] not in ("Admin", "Pharmacist"):
        return jsonify({"error": "Permission denied"}), 403
    data = request.json
    conn = get_db()
    conn.execute(
        "UPDATE medicines SET name=?,category=?,quantity=?,min_stock=?,expiry_date=?,supplier=?,price=? WHERE id=?",
        (data["name"], data.get("category",""), int(data.get("quantity",0)),
         int(data.get("min_stock",10)), data.get("expiry_date",""),
         data.get("supplier",""), float(data.get("price",0)), mid)
    )
    conn.commit()
    conn.close()
    log_activity("Edit Medicine", f"ID {mid} updated", session["user"])
    return jsonify({"success": True})

@app.route("/api/medicines/<int:mid>", methods=["DELETE"])
def api_delete_medicine(mid):
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    if session["role"] != "Admin":
        return jsonify({"error": "Only Admin can delete"}), 403
    conn = get_db()
    row = conn.execute("SELECT name FROM medicines WHERE id=?", (mid,)).fetchone()
    conn.execute("DELETE FROM medicines WHERE id=?", (mid,))
    conn.commit()
    conn.close()
    log_activity("Delete Medicine", row["name"] if row else f"ID {mid}", session["user"])
    return jsonify({"success": True})

@app.route("/api/alerts")
def api_alerts():
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    today = date.today().isoformat()
    conn = get_db()
    low     = conn.execute("SELECT id,name,quantity,min_stock FROM medicines WHERE quantity < min_stock").fetchall()
    expired = conn.execute("SELECT id,name,expiry_date FROM medicines WHERE expiry_date <= ?", (today,)).fetchall()
    conn.close()
    alerts = []
    for r in low:
        alerts.append({"type":"low","name":r["name"],"detail":f"Only {r['quantity']} left (min {r['min_stock']})"})
    for r in expired:
        alerts.append({"type":"expired","name":r["name"],"detail":f"Expired on {r['expiry_date']}"})
    return jsonify(alerts)

@app.route("/api/activity")
def api_activity():
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    conn = get_db()
    rows = conn.execute("SELECT * FROM activity ORDER BY id DESC LIMIT 20").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/chart/category")
def api_chart_category():
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    conn = get_db()
    rows = conn.execute("SELECT category, SUM(quantity) as total FROM medicines GROUP BY category").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

# ─── MAIN ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
