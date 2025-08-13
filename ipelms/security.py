from __future__ import annotations

import secrets
import time
from functools import wraps
from typing import Callable, Any
from flask import session, request, abort, redirect, url_for, flash, current_app

# --- CSRF ---

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

# --- Auth auxiliar ---

def login_required(view: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator simples para rotas que exigem usuário autenticado."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            flash("Você precisa estar autenticado.", "warning")
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped

# --- Rate limiting simples (em memória) ---

def rate_limit(max_requests: int = 8, window_seconds: int = 60) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Limita chamadas por (IP + endpoint) dentro de uma janela deslizante.
    Armazena contadores em current_app.config['_RATE_LIMIT_STORE'] (reset ao reiniciar).
    """
    def decorator(view: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(view)
        def wrapper(*args, **kwargs):
            ip = request.headers.get("X-Forwarded-For", request.remote_addr) or "unknown"
            key = f"{ip}:{request.endpoint or 'unknown'}"
            store = current_app.config.setdefault("_RATE_LIMIT_STORE", {})
            now = time.time()
            data = store.get(key)
            if not data or now - data["window_start"] > window_seconds:
                store[key] = {"count": 1, "window_start": now}
            else:
                data["count"] += 1
                if data["count"] > max_requests:
                    current_app.logger.warning("Rate limit excedido: key=%s endpoint=%s", key, request.endpoint)
                    abort(429, description="Muitas requisições; tente novamente em breve.")
            return view(*args, **kwargs)
        return wrapper
    return decorator