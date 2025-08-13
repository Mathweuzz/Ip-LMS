from __future__ import annotations

import click
import sqlite3
from pathlib import Path
from typing import List, Tuple
from flask import current_app

def _db_path() -> Path:
    return Path(current_app.config["DATABASE_PATH"])

def _migrations_dir() -> Path:
    # raiz do projeto = ipelms/../
    return Path(__file__).resolve().parent.parent / "migrations"

def _ensure_table(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations(
            version TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

def _list_migration_files() -> List[Tuple[str, str, Path]]:
    """Retorna [(version, name, path)] ordenado lexicograficamente."""
    items: List[Tuple[str, str, Path]] = []
    for p in sorted(_migrations_dir().glob("[0-9][0-9][0-9][0-9]_*.sql")):
        stem = p.stem  # ex: 0001_initial
        version, name = stem.split("_", 1)
        items.append((version, name, p))
    return items

def _applied_versions(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
    return {r[0] for r in rows}

def register_cli(app):
    @app.cli.command("db-status")
    def db_status():
        """Mostra versão atual e migrações pendentes."""
        dbp = _db_path()
        print(f"Database: {dbp}")
        with sqlite3.connect(dbp) as conn:
            conn.row_factory = sqlite3.Row
            _ensure_table(conn)
            all_migs = _list_migration_files()
            applied = _applied_versions(conn)
            pending = [m for m in all_migs if m[0] not in applied]
            curr = max(applied) if applied else "(nenhuma)"
            print(f"Versão atual: {curr}")
            if pending:
                print("Pendentes:")
                for v, name, _ in pending:
                    print(f"  - {v}_{name}.sql")
            else:
                print("Nenhuma migração pendente.")

    @app.cli.command("db-history")
    def db_history():
        """Lista histórico de migrações aplicadas."""
        with sqlite3.connect(_db_path()) as conn:
            conn.row_factory = sqlite3.Row
            _ensure_table(conn)
            rows = conn.execute("SELECT version, name, applied_at FROM schema_migrations ORDER BY applied_at").fetchall()
            if not rows:
                print("Sem histórico (tabela vazia).")
                return
            for r in rows:
                print(f"{r['version']}  {r['name']}  @ {r['applied_at']}")

    @app.cli.command("db-upgrade")
    def db_upgrade():
        """Aplica todas as migrações pendentes."""
        migs = _list_migration_files()
        if not migs:
            print("Nenhuma migração encontrada em migrations/.")
            return
        with sqlite3.connect(_db_path()) as conn:
            conn.row_factory = sqlite3.Row
            _ensure_table(conn)
            applied = _applied_versions(conn)
            to_apply = [m for m in migs if m[0] not in applied]
            if not to_apply:
                print("Nada a aplicar.")
                return
            for v, name, path in to_apply:
                sql = path.read_text(encoding="utf-8")
                print(f"Aplicando {path.name} ...")
                try:
                    with conn:
                        conn.executescript(sql)
                        conn.execute("INSERT INTO schema_migrations(version, name) VALUES (?,?)", (v, name))
                except sqlite3.Error as e:
                    print(f"ERRO na migração {path.name}: {e}")
                    raise SystemExit(1)
            print("OK: migrações aplicadas.")

    @app.cli.command("db-baseline")
    @click.option("--to", "target", required=True, help="Versão a marcar como aplicada (ex.: 0001)")
    def db_baseline(target: str):
        """Marca uma versão como já aplicada (não roda SQL). Use em bases existentes."""
        migs = {v: n for v, n, _ in _list_migration_files()}
        if target not in migs:
            print(f"Versão {target} não encontrada em migrations/.")
            raise SystemExit(1)
        with sqlite3.connect(_db_path()) as conn:
            _ensure_table(conn)
            with conn:
                conn.execute("INSERT OR IGNORE INTO schema_migrations(version, name) VALUES (?,?)", (target, migs[target]))
        print(f"Baseline marcada: {target}_{migs[target]}.sql")

    @app.cli.command("db-verify")
    def db_verify():
        """Roda PRAGMA integrity_check e exibe resultado."""
        with sqlite3.connect(_db_path()) as conn:
            res = conn.execute("PRAGMA integrity_check").fetchone()[0]
            print(f"PRAGMA integrity_check => {res}")