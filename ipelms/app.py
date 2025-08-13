from __future__ import annotations

import json
import logging
import secrets
import time
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from flask import Flask, render_template, jsonify, g, request

from . import db as db_module
from .auth import bp as auth_bp
from .courses import bp as courses_bp
from .lessons import bp as lessons_bp
from .notices import bp as notices_bp
from .assignments import bp as assignments_bp
from .security import login_required

VERSION = "0.11.0"

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
        "ACCESS_LOG": root / "logs" / "access.log",
    }
    paths["LOG_DIR"].mkdir(parents=True, exist_ok=True)
    paths["UPLOADS_DIR"].mkdir(parents=True, exist_ok=True)
    paths["INSTANCE_DIR"].mkdir(parents=True, exist_ok=True)
    return paths

def _setup_logging(app: Flask, app_log_file: Path) -> None:
    # Evita duplicar handlers
    if any(isinstance(h, RotatingFileHandler) for h in app.logger.handlers):
        return
    app.logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(app_log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    fmt = logging.Formatter(fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")
    handler.setFormatter(fmt)
    app.logger.addHandler(handler)

def _setup_access_logging(access_log_file: Path) -> logging.Logger:
    logger = logging.getLogger("ipelms.access")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(access_log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    # Para access.log, queremos apenas a mensagem crua (linha já formatada por nós)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.propagate = False  # não subir para root
    return logger

def create_app():
    root = Path(__file__).resolve().parent.parent
    paths = _setup_dirs(root)

    cfg = _load_json_config(paths["CONFIG_JSON"])
    secret_key = _load_secret_key(paths["SECRET_FILE"])

    app = Flask(__name__, instance_path=str(paths["INSTANCE_DIR"]))
    is_prod = cfg.get("environment") == "production"

    app.config.update(
        SECRET_KEY=secret_key,
        MAX_CONTENT_LENGTH=10 * 1024 * 1024,  # 10 MB
        UPLOAD_FOLDER=str(paths["UPLOADS_DIR"]),
        ENVIRONMENT=cfg.get("environment", "development"),
        SITE_NAME=cfg.get("site_name", "IpêLMS"),
        DATABASE_PATH=str((root / "data.db").resolve()),
        # Cookies de sessão reforçados:
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=is_prod,  # em produção, exigir HTTPS
    )

    app.jinja_env.globals["SITE_NAME"] = app.config["SITE_NAME"]

    # Logging de app e de acesso
    _setup_logging(app, paths["APP_LOG"])
    access_logger = _setup_access_logging(paths["ACCESS_LOG"])

    app.logger.info(
        "IpêLMS iniciado | env=%s | uploads=%s | logs=%s | version=%s",
        app.config["ENVIRONMENT"], app.config["UPLOAD_FOLDER"], paths["LOG_DIR"], VERSION
    )

    # DB + CLI
    db_module.init_app(app)

    # Blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(courses_bp)
    app.register_blueprint(lessons_bp)
    app.register_blueprint(notices_bp)
    app.register_blueprint(assignments_bp)

    # ---------- Ciclo de request: req_id + tempo + headers de segurança ----------

    @app.before_request
    def _start_timer_and_reqid():
        g._start_ts = time.perf_counter()
        g.req_id = secrets.token_hex(8)  # 16 hex chars
        # Pode ser útil ter IP resolvido cedo
        g.client_ip = request.headers.get("X-Forwarded-For", request.remote_addr) or "-"

    @app.after_request
    def _security_headers_and_access_log(resp):
        # ---- Security headers ----
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        resp.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "img-src 'self' data:; "
            "style-src 'self'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "frame-ancestors 'none'"
        )
        if app.config["ENVIRONMENT"] == "production":
            resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains; preload")

        # ---- X-Request-ID ----
        req_id = getattr(g, "req_id", None)
        if req_id:
            resp.headers["X-Request-ID"] = req_id

        # ---- Access log ----
        try:
            # Tempo
            start_ts = getattr(g, "_start_ts", None)
            rt_ms = (time.perf_counter() - start_ts) * 1000 if start_ts else -1

            # Caminho + query
            if request.query_string:
                path_qs = f"{request.path}?{request.query_string.decode(errors='ignore')}"
            else:
                path_qs = request.path

            # Protocolo e bytes
            proto = request.environ.get("SERVER_PROTOCOL", "HTTP/1.1")
            length = resp.calculate_content_length()
            length = length if length is not None else resp.headers.get("Content-Length", "-")

            # Identidade
            user_id = getattr(g, "user", None)["id"] if getattr(g, "user", None) else "-"
            referer = request.headers.get("Referer", "-")
            ua = request.headers.get("User-Agent", "-")
            ip = getattr(g, "client_ip", request.remote_addr) or "-"

            # Data no estilo CLF (UTC)
            now = datetime.now(timezone.utc).strftime("%d/%b/%Y:%H:%M:%S %z")

            line = (f'{ip} - {user_id} [{now}] "{request.method} {path_qs} {proto}" '
                    f'{resp.status_code} {length} "{referer}" "{ua}" rt={rt_ms:.2f}ms req_id={req_id or "-"}')

            logging.getLogger("ipelms.access").info(line)
        except Exception as e:
            # Não quebrar a resposta por causa de logging
            app.logger.warning("Falha ao logar acesso: %s", e)

        return resp

    @app.teardown_request
    def _log_teardown(exc):
        # Se houve exceção não tratada, registre junto do req_id
        if exc is not None:
            app.logger.exception("Unhandled error req_id=%s path=%s", getattr(g, "req_id", "-"), request.path)

    # ----- Rotas principais -----
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

    @app.errorhandler(403)
    def forbidden(err):
        return render_template("errors/403.html", err=err), 403

    @app.errorhandler(404)
    def not_found(err):
        return render_template("errors/404.html", err=err), 404

    @app.errorhandler(400)
    def bad_request(err):
        return render_template("errors/400.html", err=err), 400

    @app.errorhandler(413)
    def too_large(err):
        return render_template("errors/413.html", err=err), 413

    @app.errorhandler(429)
    def too_many(err):
        return render_template("errors/429.html", err=err), 429

    @app.errorhandler(500)
    def server_error(err):
        return render_template("errors/500.html", err=err), 500

    return app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)