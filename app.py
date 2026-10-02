from flask import (Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_from_directory)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
import uuid

app = Flask(__name__)
app.secret_key = "change-this-secret-key"
DB = Path("prahari.db")

UPLOAD_FOLDER = Path("uploads")
UPLOAD_FOLDER.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {
    "jpg", "jpeg", "png",
    "mp4", "mov", "webm",
    "mp3", "wav", "m4a"
}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS emergency_contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            relationship TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            incident_type TEXT NOT NULL DEFAULT 'SOS',
            status TEXT NOT NULL DEFAULT 'ACTIVE',
            latitude REAL,
            longitude REAL,
            location_accuracy REAL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id TEXT UNIQUE NOT NULL,
            user_id INTEGER NOT NULL,
            incident_type TEXT NOT NULL,
            description TEXT NOT NULL,
            latitude REAL,
            longitude REAL,
            location_accuracy REAL,
            evidence_file TEXT,
            evidence_type TEXT,
            status TEXT NOT NULL DEFAULT 'SUBMITTED',
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)
    conn.commit()
    conn.close()

def login_required():
    return "user_id" in session

def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        if not name or not email or len(password) < 6:
            flash("Please enter valid details. Password must be at least 6 characters.")
            return redirect(url_for("register"))

        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO users (name, email, password) VALUES (?, ?, ?)",
                (name, email, generate_password_hash(password))
            )
            conn.commit()
            flash("Account created. Please log in.")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("An account with this email already exists.")
            return redirect(url_for("register"))
        finally:
            conn.close()

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            return redirect(url_for("dashboard"))

        flash("Invalid email or password.")

    return render_template("login.html")

@app.route("/dashboard")
def dashboard():
    if not login_required():
        return redirect(url_for("login"))

    conn = get_db()
    contacts = conn.execute(
        "SELECT * FROM emergency_contacts WHERE user_id = ? ORDER BY id DESC",
        (session["user_id"],)
    ).fetchall()
    active = conn.execute(
        "SELECT * FROM incidents WHERE user_id = ? AND status = 'ACTIVE' ORDER BY id DESC LIMIT 1",
        (session["user_id"],)
    ).fetchone()
    conn.close()

    return render_template(
        "dashboard.html",
        name=session["user_name"],
        contacts=contacts,
        active_incident=active
    )

@app.route("/contacts", methods=["GET", "POST"])
def contacts():
    if not login_required():
        return redirect(url_for("login"))

    if request.method == "POST":
        name = request.form["name"].strip()
        phone = request.form["phone"].strip()
        relationship = request.form.get("relationship", "").strip()

        if not name or not phone:
            flash("Name and phone number are required.")
            return redirect(url_for("contacts"))

        conn = get_db()
        conn.execute(
            "INSERT INTO emergency_contacts (user_id, name, phone, relationship) VALUES (?, ?, ?, ?)",
            (session["user_id"], name, phone, relationship)
        )
        conn.commit()
        conn.close()
        flash("Emergency contact added.")
        return redirect(url_for("contacts"))

    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM emergency_contacts WHERE user_id = ? ORDER BY id DESC",
        (session["user_id"],)
    ).fetchall()
    conn.close()
    return render_template("contacts.html", contacts=rows)

@app.route("/report", methods=["GET", "POST"])
def report_incident():
    if not login_required():
        return redirect(url_for("login"))

    if request.method == "POST":
        incident_type = request.form.get("incident_type", "").strip()
        description = request.form.get("description", "").strip()

        latitude = request.form.get("latitude")
        longitude = request.form.get("longitude")
        accuracy = request.form.get("accuracy")

        if not incident_type or not description:
            flash("Incident type and description are required.")
            return redirect(url_for("report_incident"))

        evidence_file = request.files.get("evidence")
        saved_filename = None
        evidence_type = None

        if evidence_file and evidence_file.filename:
            if not allowed_file(evidence_file.filename):
                flash("This file type is not supported.")
                return redirect(url_for("report_incident"))

            original_name = secure_filename(evidence_file.filename)
            extension = original_name.rsplit(".", 1)[1].lower()

            saved_filename = f"{uuid.uuid4().hex}.{extension}"
            evidence_file.save(
                app.config["UPLOAD_FOLDER"] / saved_filename
            )

            if extension in {"jpg", "jpeg", "png"}:
                evidence_type = "IMAGE"
            elif extension in {"mp4", "mov", "webm"}:
                evidence_type = "VIDEO"
            else:
                evidence_type = "AUDIO"

        case_id = f"PRH-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        created_at = datetime.now(timezone.utc).isoformat()

        conn = get_db()

        conn.execute(
            """
            INSERT INTO reports
            (
                case_id,
                user_id,
                incident_type,
                description,
                latitude,
                longitude,
                location_accuracy,
                evidence_file,
                evidence_type,
                status,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'SUBMITTED', ?)
            """,
            (
                case_id,
                session["user_id"],
                incident_type,
                description,
                latitude,
                longitude,
                accuracy,
                saved_filename,
                evidence_type,
                created_at
            )
        )

        conn.commit()
        conn.close()

        return redirect(url_for("case_submitted", case_id=case_id))

    return render_template("report.html")

@app.route("/case-submitted/<case_id>")
def case_submitted(case_id):
    if not login_required():
        return redirect(url_for("login"))

    conn = get_db()

    report = conn.execute(
        """
        SELECT *
        FROM reports
        WHERE case_id = ? AND user_id = ?
        """,
        (case_id, session["user_id"])
    ).fetchone()

    conn.close()

    if not report:
        return "Case not found", 404

    return render_template(
        "case_submitted.html",
        report=report
    )

@app.post("/api/sos")
def create_sos():
    if not login_required():
        return jsonify({"ok": False, "error": "Login required"}), 401

    data = request.get_json(silent=True) or {}
    latitude = data.get("latitude")
    longitude = data.get("longitude")
    accuracy = data.get("accuracy")

    conn = get_db()

    existing = conn.execute(
        "SELECT * FROM incidents WHERE user_id = ? AND status = 'ACTIVE' ORDER BY id DESC LIMIT 1",
        (session["user_id"],)
    ).fetchone()

    if existing:
        conn.close()
        return jsonify({
            "ok": True,
            "incident_id": existing["id"],
            "message": "An active SOS already exists."
        })

    created_at = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        """INSERT INTO incidents
           (user_id, incident_type, status, latitude, longitude, location_accuracy, created_at)
           VALUES (?, 'SOS', 'ACTIVE', ?, ?, ?, ?)""",
        (session["user_id"], latitude, longitude, accuracy, created_at)
    )
    conn.commit()
    incident_id = cur.lastrowid
    conn.close()

    return jsonify({
        "ok": True,
        "incident_id": incident_id,
        "message": "SOS incident created.",
        "location_received": latitude is not None and longitude is not None
    })

@app.post("/api/sos/<int:incident_id>/resolve")
def resolve_sos(incident_id):
    if not login_required():
        return jsonify({"ok": False, "error": "Login required"}), 401

    conn = get_db()
    cur = conn.execute(
        "UPDATE incidents SET status = 'RESOLVED' WHERE id = ? AND user_id = ? AND status = 'ACTIVE'",
        (incident_id, session["user_id"])
    )
    conn.commit()
    conn.close()

    if cur.rowcount == 0:
        return jsonify({"ok": False, "error": "Active incident not found."}), 404

    return jsonify({"ok": True, "message": "SOS marked resolved."})

@app.route("/cases")
def cases():
    if not login_required():
        return redirect(url_for("login"))

    conn = get_db()

    reports = conn.execute(
        """
        SELECT *
        FROM reports
        WHERE user_id = ?
        ORDER BY created_at DESC
        """,
        (session["user_id"],)
    ).fetchall()

    conn.close()

    return render_template(
        "cases.html",
        reports=reports
    )

@app.route("/safety-map")
def safety_map():
    if not login_required():
        return redirect(url_for("login"))

    return render_template("safety_map.html")

@app.route("/case/<case_id>")
def case_detail(case_id):
    if not login_required():
        return redirect(url_for("login"))

    conn = get_db()

    report = conn.execute(
        """
        SELECT *
        FROM reports
        WHERE case_id = ? AND user_id = ?
        """,
        (case_id, session["user_id"])
    ).fetchone()

    conn.close()

    if not report:
        return "Case not found", 404

    return render_template(
        "case_detail.html",
        report=report
    )

@app.route("/evidence/<case_id>")
def view_evidence(case_id):
    if not login_required():
        return redirect(url_for("login"))

    conn = get_db()

    report = conn.execute(
        """
        SELECT evidence_file
        FROM reports
        WHERE case_id = ? AND user_id = ?
        """,
        (case_id, session["user_id"])
    ).fetchone()

    conn.close()

    if not report:
        return "Case not found", 404

    if not report["evidence_file"]:
        return "No evidence attached to this case.", 404

    evidence_path = Path(app.config["UPLOAD_FOLDER"])

    return send_from_directory(
        evidence_path,
        report["evidence_file"],
        as_attachment=False
    )

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
