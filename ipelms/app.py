from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from flask import Flask, render_template, jsonify, g

from . import db as db_module
from .auth import bp as auth_bp
from .courses import bp as courses_bp
from .lessons import bp as lessons_bp
from .notices import bp as notices_bp
from .security import login_required

VERSION = "0.8.0"

def _load_json_config(config_path: Path) -> dict:
    default = {"site_name": "IpêLMS", "environment": "development"}
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return default
        data.setdefault("site_name", "IpêLMS")
        data.setdefault("environment", "development")
        return data
    except Exception:
        return default

def _load_secret_key(secret_path: Path) -> str:
    try:
        key = secret_path.read_text(encoding="utf-8").strip()
        return key if len(key) >= 32 else "dev"
    except Exception:
        return "dev"

def _setup_dirs(root: Path) -> dict[str, Path]:
    paths = {
        "LOG_DIR": root / "logs",
        "UPLOADS_DIR": root / "uploads",
        "INSTANCE_DIR": root / "instance",
        "CONFIG_JSON": root / "config" / "config.json",
        "SECRET_FILE": root / "config" / "secret_key.txt",
        "APP_LOG": root / "logs" / "app.log",
    }
    paths["LOG_DIR"].mkdir(parents=True, exist_ok=True)
    paths["UPLOADS_DIR"].mkdir(parents=True, exist_ok=True)
    paths["INSTANCE_DIR"].mkdir(parents=True, exist_ok=True)
    return paths

def _setup_logging(app: Flask, log_file: Path) -> None:
    if any(isinstance(h, RotatingFileHandler) for h in app.logger.handlers):
        return
    app.logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(
        log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    fmt = logging.Formatter(
        fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(fmt)
    app.logger.addHandler(handler)

def create_app():
    root = Path(__file__).resolve().parent.parent
    paths = _setup_dirs(root)

    cfg = _load_json_config(paths["CONFIG_JSON"])
    secret_key = _load_secret_key(paths["SECRET_FILE"])

    app = Flask(__name__, instance_path=str(paths["INSTANCE_DIR"]))
    app.config.update(
        SECRET_KEY=secret_key,
        MAX_CONTENT_LENGTH=10 * 1024 * 1024,  # 10 MB
        UPLOAD_FOLDER=str(paths["UPLOADS_DIR"]),
        ENVIRONMENT=cfg.get("environment", "development"),
        SITE_NAME=cfg.get("site_name", "IpêLMS"),
        DATABASE_PATH=str((root / "data.db").resolve()),
    )

    app.jinja_env.globals["SITE_NAME"] = app.config["SITE_NAME"]

    _setup_logging(app, paths["APP_LOG"])
    app.logger.info(
        "IpêLMS iniciado | env=%s | uploads=%s | logs=%s | version=%s",
        app.config["ENVIRONMENT"], app.config["UPLOAD_FOLDER"], paths["LOG_DIR"], VERSION
    )

    db_module.init_app(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(courses_bp)
    app.register_blueprint(lessons_bp)
    app.register_blueprint(notices_bp)

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/dashboard")
    @login_required
    def dashboard():
        my_courses = db_module.query("""
          SELECT c.* FROM courses c
          JOIN course_members m ON m.course_id = c.id
          WHERE m.user_id = ?
          ORDER BY c.created_at DESC
        """, (g.user["id"],))
        my_instr_courses = db_module.query("""
          SELECT c.* FROM courses c
          JOIN course_instructors i ON i.course_id = c.id
          WHERE i.user_id = ?
          ORDER BY c.created_at DESC
        """, (g.user["id"],))
        return render_template("dashboard.html",
                               my_courses=my_courses,
                               my_instr_courses=my_instr_courses)

    @app.get("/healthz")
    def healthz():
        return jsonify(
            status="ok",
            app="ipelms",
            version=VERSION,
            environment=app.config.get("ENVIRONMENT"),
            site_name=app.config.get("SITE_NAME"),
        )

    @app.errorhandler(404)
    def not_found(err):
        return render_template("errors/404.html", err=err), 404

    @app.errorhandler(400)
    def bad_request(err):
        return render_template("errors/400.html", err=err), 400

    @app.errorhandler(413)
    def too_large(err):
        return render_template("errors/413.html", err=err), 413

    @app.errorhandler(500)
    def server_error(err):
        return render_template("errors/500.html", err=err), 500

    return app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)