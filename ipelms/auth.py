from __future__ import annotations

import re
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, g, current_app
from werkzeug.security import generate_password_hash, check_password_hash

from .db import query, execute
from .security import csrf_protect, get_csrf_token

bp = Blueprint("auth", __name__, url_prefix="/auth")

EMAIL_RE = re.compile(r"^[^@]+@[^@]+\.[^@]+$")

@bp.before_app_request
def load_logged_in_user():
    user_id = session.get("user_id")
    if user_id is None:
        g.user = None
    else:
        g.user = query("SELECT id, name, email, role FROM users WHERE id = ?", (user_id,), one=True)

@bp.app_context_processor
def inject_user_and_csrf():
    return {"current_user": g.get("user"), "csrf_token": get_csrf_token()}


@bp.get("/register")
def register_form():
    return render_template("auth/register.html")

@bp.post("/register")
@csrf_protect
def register_post():
    name = (request.form.get("name") or "").strip()
    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""

    # Validações básicas
    if len(name) < 2:
        flash("Nome muito curto.", "danger"); return redirect(url_for("auth.register_form"))
    if not EMAIL_RE.match(email):
        flash("E-mail inválido.", "danger"); return redirect(url_for("auth.register_form"))
    if len(password) < 6:
        flash("Senha deve ter pelo menos 6 caracteres.", "danger"); return redirect(url_for("auth.register_form"))

    # Checar se email já existe
    if query("SELECT id FROM users WHERE email = ?", (email,), one=True):
        flash("E-mail já cadastrado.", "danger")
        return redirect(url_for("auth.register_form"))

    pwd_hash = generate_password_hash(password)
    user_id = execute(
        "INSERT INTO users(name, email, password_hash, role) VALUES (?, ?, ?, 'student')",
        (name, email, pwd_hash)
    )
    current_app.logger.info("Novo usuário registrado: id=%s email=%s", user_id, email)
    flash("Conta criada com sucesso! Faça login.", "success")
    return redirect(url_for("auth.login"))


@bp.get("/login")
def login():
    return render_template("auth/login.html")

@bp.post("/login")
@csrf_protect
def login_post():
    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""
    user = query("SELECT id, name, email, password_hash, role FROM users WHERE email = ?", (email,), one=True)
    if not user or not check_password_hash(user["password_hash"], password):
        flash("Credenciais inválidas.", "danger")
        return redirect(url_for("auth.login"))
    session.clear()
    session["user_id"] = user["id"]
    current_app.logger.info("Login bem-sucedido: id=%s email=%s", user["id"], user["email"])
    flash(f"Bem-vindo, {user['name']}!", "success")
    next_url = request.args.get("next") or url_for("index")
    return redirect(next_url)


@bp.get("/logout")
def logout():
    if session.get("user_id"):
        current_app.logger.info("Logout: user_id=%s", session["user_id"])
    session.clear()
    flash("Você saiu da sessão.", "info")
    return redirect(url_for("index"))