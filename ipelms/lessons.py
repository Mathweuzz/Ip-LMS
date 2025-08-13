from __future__ import annotations

import os
from pathlib import Path
from typing import Optional
from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, g,
    current_app, send_from_directory, abort
)
from werkzeug.utils import secure_filename

from .db import query, execute
from .security import login_required, csrf_protect

bp = Blueprint("lessons", __name__, url_prefix="/lessons")

ALLOWED_EXT = {"pdf", "txt", "md", "png", "jpg", "jpeg", "gif", "zip", "pptx", "docx", "csv"}


def _get_course(course_id: int) -> Optional[dict]:
    return query("SELECT * FROM courses WHERE id = ?", (course_id,), one=True)

def _get_lesson(lesson_id: int) -> Optional[dict]:
    return query("SELECT * FROM lessons WHERE id = ?", (lesson_id,), one=True)

def _is_instructor(user_id: int, course_id: int) -> bool:
    row = query("SELECT 1 FROM course_instructors WHERE course_id=? AND user_id=?", (course_id, user_id), one=True)
    return bool(row)

def _is_member(user_id: int, course_id: int) -> bool:
    row = query("SELECT 1 FROM course_members WHERE course_id=? AND user_id=?", (course_id, user_id), one=True)
    return bool(row)

def _require_instructor(course_id: int) -> Optional[dict]:
    """Garante que o usuário atual é instrutor; retorna o curso se OK."""
    if not g.get("user"):
        flash("Você precisa estar autenticado.", "warning")
        return None
    course = _get_course(course_id)
    if not course:
        flash("Curso inexistente.", "danger")
        return None
    if not _is_instructor(g.user["id"], course_id):
        flash("Apenas instrutores podem realizar esta ação.", "danger")
        return None
    return course

def _require_can_view(course_id: int) -> bool:
    """Instrutores e alunos matriculados podem ver/baixar."""
    if not g.get("user"):
        return False
    return _is_instructor(g.user["id"], course_id) or _is_member(g.user["id"], course_id)

def _course_lessons_dir(course_id: int) -> Path:
    base = Path(current_app.config["UPLOAD_FOLDER"])
    p = base / "courses" / str(course_id) / "lessons"
    p.mkdir(parents=True, exist_ok=True)
    return p

def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT

def _is_under_uploads(path: Path) -> bool:
    """Evita apagar/servir fora de UPLOAD_FOLDER."""
    try:
        return Path(current_app.config["UPLOAD_FOLDER"]).resolve() in path.resolve().parents
    except Exception:
        return False


@bp.get("/new/<int:course_id>")
@login_required
def new(course_id: int):
    course = _require_instructor(course_id)
    if not course:
        return redirect(url_for("courses.detail", course_id=course_id))
    return render_template("lessons/new.html", course=course)

@bp.post("/create/<int:course_id>")
@login_required
@csrf_protect
def create(course_id: int):
    course = _require_instructor(course_id)
    if not course:
        return redirect(url_for("courses.detail", course_id=course_id))

    title = (request.form.get("title") or "").strip()
    content = (request.form.get("content") or "").strip()

    if len(title) < 3:
        flash("Título muito curto.", "danger")
        return redirect(url_for("lessons.new", course_id=course_id))

    # 1) Cria a aula sem anexo
    lesson_id = execute(
        "INSERT INTO lessons(course_id, title, content, created_by) VALUES (?,?,?,?)",
        (course_id, title, content, g.user["id"])
    )

    # 2) Se houver arquivo, salva e atualiza o caminho
    file = request.files.get("attachment")
    if file and file.filename:
        filename = secure_filename(file.filename)
        if not _allowed_file(filename):
            flash("Extensão de arquivo não permitida.", "danger")
            return redirect(url_for("lessons.new", course_id=course_id))
        # caminho: uploads/courses/<course_id>/lessons/lesson_<id>__<filename>
        dest_dir = _course_lessons_dir(course_id)
        final_name = f"lesson_{lesson_id}__{filename}"
        dest_path = dest_dir / final_name
        file.save(dest_path)
        rel_path = dest_path.relative_to(Path(current_app.config["UPLOAD_FOLDER"]))
        execute("UPDATE lessons SET attachment_path=? WHERE id=?", (str(rel_path), lesson_id))
        current_app.logger.info("Upload anexo: lesson=%s file=%s", lesson_id, dest_path)

    flash("Aula criada com sucesso!", "success")
    return redirect(url_for("courses.detail", course_id=course_id))

@bp.get("/<int:lesson_id>")
@login_required
def detail(lesson_id: int):
    lesson = _get_lesson(lesson_id)
    if not lesson:
        flash("Aula não encontrada.", "danger")
        return redirect(url_for("courses.list_courses"))
    if not _require_can_view(lesson["course_id"]):
        flash("Você não tem acesso a esta aula.", "danger")
        return redirect(url_for("courses.detail", course_id=lesson["course_id"]))
    is_instr = _is_instructor(g.user["id"], lesson["course_id"])
    return render_template("lessons/detail.html", lesson=lesson, is_instr=is_instr)

@bp.get("/<int:lesson_id>/edit")
@login_required
def edit(lesson_id: int):
    lesson = _get_lesson(lesson_id)
    if not lesson:
        flash("Aula não encontrada.", "danger")
        return redirect(url_for("courses.list_courses"))
    course = _require_instructor(lesson["course_id"])
    if not course:
        return redirect(url_for("courses.detail", course_id=lesson["course_id"]))
    return render_template("lessons/edit.html", lesson=lesson, course=course)

@bp.post("/<int:lesson_id>/edit")
@login_required
@csrf_protect
def edit_post(lesson_id: int):
    lesson = _get_lesson(lesson_id)
    if not lesson:
        flash("Aula não encontrada.", "danger")
        return redirect(url_for("courses.list_courses"))
    course = _require_instructor(lesson["course_id"])
    if not course:
        return redirect(url_for("courses.detail", course_id=lesson["course_id"]))

    title = (request.form.get("title") or "").strip()
    content = (request.form.get("content") or "").strip()
    if len(title) < 3:
        flash("Título muito curto.", "danger")
        return redirect(url_for("lessons.edit", lesson_id=lesson_id))

    execute("UPDATE lessons SET title=?, content=? WHERE id=?", (title, content, lesson_id))

    # Substituir anexo se novo arquivo for enviado
    file = request.files.get("attachment")
    if file and file.filename:
        filename = secure_filename(file.filename)
        if not _allowed_file(filename):
            flash("Extensão de arquivo não permitida.", "danger")
            return redirect(url_for("lessons.edit", lesson_id=lesson_id))
        dest_dir = _course_lessons_dir(lesson["course_id"])
        final_name = f"lesson_{lesson_id}__{filename}"
        dest_path = dest_dir / final_name
        file.save(dest_path)
        rel_path = dest_path.relative_to(Path(current_app.config["UPLOAD_FOLDER"]))

        # remover arquivo antigo (se havia)
        old = lesson["attachment_path"]
        if old:
            old_abs = Path(current_app.config["UPLOAD_FOLDER"]) / old
            if old_abs.exists() and _is_under_uploads(old_abs):
                try:
                    old_abs.unlink()
                except Exception:
                    current_app.logger.warning("Falha ao remover anexo antigo: %s", old_abs)

        execute("UPDATE lessons SET attachment_path=? WHERE id=?", (str(rel_path), lesson_id))
        current_app.logger.info("Substituído anexo: lesson=%s file=%s", lesson_id, dest_path)

    flash("Aula atualizada.", "success")
    return redirect(url_for("lessons.detail", lesson_id=lesson_id))

@bp.post("/<int:lesson_id>/delete")
@login_required
@csrf_protect
def delete(lesson_id: int):
    lesson = _get_lesson(lesson_id)
    if not lesson:
        flash("Aula não encontrada.", "danger")
        return redirect(url_for("courses.list_courses"))
    course = _require_instructor(lesson["course_id"])
    if not course:
        return redirect(url_for("courses.detail", course_id=lesson["course_id"]))

    # remover arquivo, se houver
    if lesson["attachment_path"]:
        abs_path = Path(current_app.config["UPLOAD_FOLDER"]) / lesson["attachment_path"]
        if abs_path.exists() and _is_under_uploads(abs_path):
            try:
                abs_path.unlink()
            except Exception:
                current_app.logger.warning("Falha ao remover anexo: %s", abs_path)

    execute("DELETE FROM lessons WHERE id=?", (lesson_id,))
    flash("Aula excluída.", "info")
    return redirect(url_for("courses.detail", course_id=lesson["course_id"]))

@bp.get("/download/<int:lesson_id>")
@login_required
def download(lesson_id: int):
    lesson = _get_lesson(lesson_id)
    if not lesson:
        abort(404)
    if not _require_can_view(lesson["course_id"]):
        abort(403)
    if not lesson["attachment_path"]:
        abort(404)
    abs_path = Path(current_app.config["UPLOAD_FOLDER"]) / lesson["attachment_path"]
    if not abs_path.exists():
        abort(404)
    if not _is_under_uploads(abs_path):
        abort(403)
    directory = abs_path.parent
    filename = abs_path.name
    return send_from_directory(directory, filename, as_attachment=True)