from __future__ import annotations

import secrets
from functools import wraps
from typing import Callable, Any
from flask import session, request, abort, redirect, url_for, flash


def get_csrf_token() -> str:
    """Garante e retorna um token CSRF armazenado na sessão."""
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token

def csrf_protect(view: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator que exige um token CSRF válido para métodos mutáveis."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            form_token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
            if not form_token or form_token != session.get("csrf_token"):
                abort(400, description="CSRF token inválido ou ausente.")
        return view(*args, **kwargs)
    return wrapper


def login_required(view: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator simples para rotas que exigem usuário autenticado."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            flash("Você precisa estar autenticado.", "warning")
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped