from __future__ import annotations

import re
from typing import Optional
from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, g, current_app
)
from .db import query, execute
from .security import login_required, csrf_protect

bp = Blueprint("courses", __name__, url_prefix="/courses")

CODE_RE = re.compile(r"^[A-Z0-9-]{3,10}$")

def _get_course(course_id: int) -> Optional[dict]:
    return query("SELECT * FROM courses WHERE id = ?", (course_id,), one=True)

def _is_instructor(user_id: int, course_id: int) -> bool:
    row = query("SELECT 1 FROM course_instructors WHERE course_id=? AND user_id=?", (course_id, user_id), one=True)
    return bool(row)

def _is_member(user_id: int, course_id: int) -> bool:
    row = query("SELECT 1 FROM course_members WHERE course_id=? AND user_id=?", (course_id, user_id), one=True)
    return bool(row)

@bp.get("/")
def list_courses():
    courses = query("""
        SELECT c.*, u.name AS owner_name
        FROM courses c
        JOIN users u ON u.id = c.created_by
        ORDER BY c.created_at DESC
    """)
    return render_template("courses/list.html", courses=courses)

@bp.get("/new")
@login_required
def new_course():
    return render_template("courses/new.html")

@bp.post("/")
@login_required
@csrf_protect
def create_course():
    title = (request.form.get("title") or "").strip()
    description = (request.form.get("description") or "").strip()
    code = (request.form.get("code") or "").strip().upper()

    if len(title) < 3:
        flash("Título muito curto.", "danger"); return redirect(url_for("courses.new_course"))
    if not CODE_RE.match(code):
        flash("Código inválido (use A-Z, 0-9, '-' e 3–10 chars).", "danger"); return redirect(url_for("courses.new_course"))

    if query("SELECT id FROM courses WHERE code = ?", (code,), one=True):
        flash("Já existe um curso com esse código.", "danger"); return redirect(url_for("courses.new_course"))

    course_id = execute(
        "INSERT INTO courses(title, description, code, created_by) VALUES (?, ?, ?, ?)",
        (title, description, code, g.user["id"])
    )
    execute("INSERT OR IGNORE INTO course_instructors(course_id, user_id) VALUES (?, ?)", (course_id, g.user["id"]))
    current_app.logger.info("Curso criado: id=%s code=%s by user_id=%s", course_id, code, g.user["id"])
    flash("Curso criado com sucesso!", "success")
    return redirect(url_for("courses.detail", course_id=course_id))

@bp.get("/<int:course_id>")
def detail(course_id: int):
    course = _get_course(course_id)
    if not course:
        flash("Curso não encontrado.", "danger")
        return redirect(url_for("courses.list_courses"))

    instructors = query("""
        SELECT u.id, u.name, u.email
        FROM course_instructors ci
        JOIN users u ON u.id = ci.user_id
        WHERE ci.course_id = ?
        ORDER BY u.name
    """, (course_id,))

    members_count = query("SELECT COUNT(*) AS c FROM course_members WHERE course_id = ?", (course_id,), one=True)["c"]

    lessons = query("""
        SELECT id, title, created_at, attachment_path
        FROM lessons
        WHERE course_id = ?
        ORDER BY created_at DESC
    """, (course_id,))

    notices = query("""
        SELECT id, title, created_at
        FROM notices
        WHERE course_id = ?
        ORDER BY created_at DESC
    """, (course_id,))

    assignments = query("""
        SELECT id, title, created_at
        FROM assignments
        WHERE course_id = ?
        ORDER BY created_at DESC
    """, (course_id,))

    is_instr = False
    is_mem = False
    if g.get("user"):
        is_instr = _is_instructor(g.user["id"], course_id)
        is_mem = _is_member(g.user["id"], course_id)

    return render_template(
        "courses/detail.html",
        course=course,
        instructors=instructors,
        members_count=members_count,
        lessons=lessons,
        notices=notices,
        assignments=assignments,
        is_instr=is_instr,
        is_mem=is_mem
    )

@bp.post("/<int:course_id>/join")
@login_required
@csrf_protect
def join(course_id: int):
    course = _get_course(course_id)
    if not course:
        flash("Curso inexistente.", "danger"); return redirect(url_for("courses.list_courses"))
    if query("SELECT 1 FROM course_members WHERE course_id=? AND user_id=?", (course_id, g.user["id"]), one=True):
        flash("Você já está matriculado neste curso.", "info")
        return redirect(url_for("courses.detail", course_id=course_id))
    execute("INSERT INTO course_members(course_id, user_id) VALUES (?,?)", (course_id, g.user["id"]))
    current_app.logger.info("Matrícula: course=%s user=%s", course_id, g.user["id"])
    flash("Você entrou no curso.", "success")
    return redirect(url_for("courses.detail", course_id=course_id))

@bp.post("/<int:course_id>/leave")
@login_required
@csrf_protect
def leave(course_id: int):
    course = _get_course(course_id)
    if not course:
        flash("Curso inexistente.", "danger"); return redirect(url_for("courses.list_courses"))
    if not query("SELECT 1 FROM course_members WHERE course_id=? AND user_id=?", (course_id, g.user["id"]), one=True):
        flash("Você não está matriculado neste curso.", "warning")
        return redirect(url_for("courses.detail", course_id=course_id))
    execute("DELETE FROM course_members WHERE course_id=? AND user_id=?", (course_id, g.user["id"]))
    current_app.logger.info("Saída do curso: course=%s user=%s", course_id, g.user["id"])
    flash("Você saiu do curso.", "info")
    return redirect(url_for("courses.detail", course_id=course_id))
