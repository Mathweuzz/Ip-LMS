from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from flask import Flask, render_template, jsonify

from . import db as db_module

VERSION = "0.3.0"

def _load_json_config(config_path: Path) -> dict:
    default = {"site_name": "IpêMLS", "environment": "development"}
    try:
        data = json.load(config_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return default
        # sane defaults
        data.setdefault("site_name", "IpêLMS")
        data.setdefault("environment", "development")
        return data
    except Exception:
        return default
    
def _load_secret_key(secret_path: Path) -> str:
    try:
        key = secret_path.read_text(encoding="utf-8").strip()
        # validação
        if len(key) < 32:
            return "dev"
        return key
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
    # evitar handlets duplucados em realod do flask
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
    # paths relativos a raiz do projeto
    root = Path(__file__).resolve().parent.parent
    paths = _setup_dirs(root)

    # carregar confis
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

    # Logging
    _setup_logging(app, paths["APP_LOG"])
    app.logger.info(
        "IpêLMS iniciado | env=%s | uploads=%s | logs=%s | version=%s",
        app.config["ENVIRONMENT"], app.config["UPLOAD_FOLDER"], paths["LOG_DIR"], VERSION
    )

    db_module.init_app(app)

    @app.get("/")
    def index():
        app.logger.info("GET / (index) acessado")
        return render_template("index.html")
    
    @app.get("/healthz")
    def healthz():
        # Retorna ambiente e nome do site para validação
        return jsonify(
            status="ok",
            app="ipelms",
            version=VERSION,
            environment=app.config.get("ENVIRONMENT"),
            site_name=app.config.get("SITE_NAME"),
        )
    
    return app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)