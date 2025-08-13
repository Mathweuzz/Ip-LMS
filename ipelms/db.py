from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable, Optional, Any
from flask import current_app, g

DB_FILENAME = "data.db"

def _db_path() -> Path:
    """retorna o caminho absluto para o arquvi do banco"""
    # current_app.root_path -> .../ipelms
    project_root = Path(current_app.root_path).parent
    return project_root / DB_FILENAME

def get_db() -> sqlite3.Connection:
    """obtem a conexao por request"""
    if "db" not in g:
        db_path = _db_path()
        conn = sqlite3.connect(
            db_path,
            detect_types=sqlite3.PARSE_DECLTYPES,
            check_same_thread=False, #enable cli do flask
        )
        conn.row_factory = sqlite3.Row
        # garantir integridade
        conn.execute("PRAGMA foreign_keys = ON;")
        g.db = conn
    return g.db

def close_db(e: Optional[BaseException] = None) -> None:
    """fecha a conexao"""
    db = g.pop("db", None)
    if db is not None:
        db.close()

def query(sql: str, params: Iterable[Any] = (), one: bool = False):
    cur = get_db().execute(sql, tuple(params))
    rows = cur.fetchall()
    cur.close()
    return (rows[0] if rows else None) if one else rows

def execute(sql: str, params: Iterable[Any] = ()) -> int:
    cur = get_db().execute(sql, tuple(params))
    get_db().commit()
    last_id = cur.lastrowid
    cur.close()
    return last_id

def executescript(script: str) -> None:
    get_db().executescript(script)
    get_db().commit()

def init_db() -> None:
    """le models.sql e cria/atualiza o schema inicial"""
    project_root = Path(current_app.root_path).parent
    schema_path = project_root / "models.sql"
    script = schema_path.read_text(encoding="utf-8")
    executescript(script)

def init_app(app) -> None:
    """regsita teardown e o comando cli init-db"""
    app.teardown_appcontext(close_db)

    import click

    @app.cli.command("init-db")
    def init_db_command():
        """inicializa o banco"""
        init_db()
        click.echo("Banco inicializado (data.db)")

