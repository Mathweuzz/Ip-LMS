from __future__ import annotations

from typing import Optional
from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, g, current_app, abort
)

from .db import query, execute
from .security import login_required, csrf_protect

bp = Blueprint("notices", __name__, url_prefix="/notices")


def _get_course(course_id: int) -> Optional[dict]:
    return query("SELECT * FROM courses WHERE id = ?", (course_id,), one=True)

def _is_instructor(user_id: int, course_id: int) -> bool:
    return bool(query(
        "SELECT 1 FROM course_instructors WHERE course_id=? AND user_id=?",
        (course_id, user_id), one=True
    ))

def _is_member(user_id: int, course_id: int) -> bool:
    return bool(query(
        "SELECT 1 FROM course_members WHERE course_id=? AND user_id=?",
        (course_id, user_id), one=True
    ))

def _can_view(user_id: int, course_id: int) -> bool:
    return _is_instructor(user_id, course_id) or _is_member(user_id, course_id)


@bp.get("/new/<int:course_id>")
@login_required
def new(course_id: int):
    course = _get_course(course_id)
    if not course:
        flash("Curso inexistente.", "danger")
        return redirect(url_for("courses.list_courses"))
    if not _is_instructor(g.user["id"], course_id):
        flash("Apenas instrutores podem criar avisos.", "danger")
        return redirect(url_for("courses.detail", course_id=course_id))
    return render_template("notices/new.html", course=course)

@bp.post("/create/<int:course_id>")
@login_required
@csrf_protect
def create(course_id: int):
    course = _get_course(course_id)
    if not course:
        flash("Curso inexistente.", "danger")
        return redirect(url_for("courses.list_courses"))
    if not _is_instructor(g.user["id"], course_id):
        flash("Apenas instrutores podem criar avisos.", "danger")
        return redirect(url_for("courses.detail", course_id=course_id))

    title = (request.form.get("title") or "").strip()
    body  = (request.form.get("body") or "").strip()

    if len(title) < 3:
        flash("Título muito curto.", "danger")
        return redirect(url_for("notices.new", course_id=course_id))
    if not body:
        flash("O corpo do aviso é obrigatório.", "danger")
        return redirect(url_for("notices.new", course_id=course_id))

    notice_id = execute(
        "INSERT INTO notices(course_id, title, body, created_by) VALUES (?,?,?,?)",
        (course_id, title, body, g.user["id"])
    )
    current_app.logger.info("Aviso criado: id=%s course=%s by user=%s", notice_id, course_id, g.user["id"])
    flash("Aviso publicado!", "success")
    return redirect(url_for("notices.detail", notice_id=notice_id))

@bp.get("/<int:notice_id>")
@login_required
def detail(notice_id: int):
    notice = query("""
        SELECT n.*, c.title AS course_title, c.code AS course_code
        FROM notices n
        JOIN courses c ON c.id = n.course_id
        WHERE n.id = ?
    """, (notice_id,), one=True)
    if not notice:
        flash("Aviso não encontrado.", "danger")
        return redirect(url_for("courses.list_courses"))
    if not _can_view(g.user["id"], notice["course_id"]):
        flash("Você não tem acesso a este aviso.", "danger")
        return redirect(url_for("courses.detail", course_id=notice["course_id"]))
    return render_template("notices/detail.html", notice=notice)