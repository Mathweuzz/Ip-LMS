from __future__ import annotations

from pathlib import Path
from typing import Optional
from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, g,
    current_app, send_from_directory, abort
)
from werkzeug.utils import secure_filename

from .db import query, execute
from .security import login_required, csrf_protect

bp = Blueprint("assignments", __name__, url_prefix="/assignments")

ALLOWED_EXT = {"pdf", "txt", "md", "png", "jpg", "jpeg", "gif", "zip", "pptx", "docx", "csv"}

# ---------- Helpers ----------
def _get_course(course_id: int) -> Optional[dict]:
    return query("SELECT * FROM courses WHERE id = ?", (course_id,), one=True)

def _get_assignment(assignment_id: int) -> Optional[dict]:
    return query("SELECT * FROM assignments WHERE id = ?", (assignment_id,), one=True)

def _is_instructor(user_id: int, course_id: int) -> bool:
    return bool(query("SELECT 1 FROM course_instructors WHERE course_id=? AND user_id=?", (course_id, user_id), one=True))

def _is_member(user_id: int, course_id: int) -> bool:
    return bool(query("SELECT 1 FROM course_members WHERE course_id=? AND user_id=?", (course_id, user_id), one=True))

def _uploads_dir(course_id: int) -> Path:
    base = Path(current_app.config["UPLOAD_FOLDER"])
    p = base / "courses" / str(course_id) / "assignments"
    p.mkdir(parents=True, exist_ok=True)
    return p

def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT

def _is_under_uploads(path: Path) -> bool:
    try:
        return Path(current_app.config["UPLOAD_FOLDER"]).resolve() in path.resolve().parents
    except Exception:
        return False

# ---------- Rotas ----------
@bp.get("/new/<int:course_id>")
@login_required
def new(course_id: int):
    course = _get_course(course_id)
    if not course:
        flash("Curso inexistente.", "danger"); return redirect(url_for("courses.list_courses"))
    if not _is_instructor(g.user["id"], course_id):
        flash("Apenas instrutores podem criar tarefas.", "danger")
        return redirect(url_for("courses.detail", course_id=course_id))
    return render_template("assignments/new.html", course=course)

@bp.post("/create/<int:course_id>")
@login_required
@csrf_protect
def create(course_id: int):
    course = _get_course(course_id)
    if not course:
        flash("Curso inexistente.", "danger"); return redirect(url_for("courses.list_courses"))
    if not _is_instructor(g.user["id"], course_id):
        flash("Apenas instrutores podem criar tarefas.", "danger")
        return redirect(url_for("courses.detail", course_id=course_id))

    title = (request.form.get("title") or "").strip()
    description = (request.form.get("description") or "").strip()
    if len(title) < 3:
        flash("Título muito curto.", "danger")
        return redirect(url_for("assignments.new", course_id=course_id))

    assignment_id = execute(
        "INSERT INTO assignments(course_id, title, description, created_by) VALUES (?,?,?,?)",
        (course_id, title, description, g.user["id"])
    )
    current_app.logger.info("Tarefa criada: id=%s course=%s by user=%s", assignment_id, course_id, g.user["id"])
    flash("Tarefa criada com sucesso!", "success")
    return redirect(url_for("assignments.detail", assignment_id=assignment_id))

@bp.get("/<int:assignment_id>")
@login_required
def detail(assignment_id: int):
    a = query("""
        SELECT a.*, c.title AS course_title, c.code AS course_code
        FROM assignments a
        JOIN courses c ON c.id = a.course_id
        WHERE a.id = ?
    """, (assignment_id,), one=True)
    if not a:
        flash("Tarefa não encontrada.", "danger")
        return redirect(url_for("courses.list_courses"))

    user_id = g.user["id"]
    can_view = _is_instructor(user_id, a["course_id"]) or _is_member(user_id, a["course_id"])
    if not can_view:
        flash("Você não tem acesso a esta tarefa.", "danger")
        return redirect(url_for("courses.detail", course_id=a["course_id"]))

    # Envio do usuário (se aluno) e lista de envios (se instrutor)
    my_submission = None
    all_submissions = None

    if _is_member(user_id, a["course_id"]):
        my_submission = query("""
            SELECT * FROM submissions WHERE assignment_id=? AND student_id=?
        """, (assignment_id, user_id), one=True)

    if _is_instructor(user_id, a["course_id"]):
        all_submissions = query("""
            SELECT s.*, u.name, u.email
            FROM submissions s
            JOIN users u ON u.id = s.student_id
            WHERE s.assignment_id=?
            ORDER BY s.submitted_at DESC
        """, (assignment_id,))

    return render_template("assignments/detail.html",
                           assignment=a,
                           my_submission=my_submission,
                           all_submissions=all_submissions,
                           is_instructor=_is_instructor(user_id, a["course_id"]))

@bp.post("/<int:assignment_id>/submit")
@login_required
@csrf_protect
def submit(assignment_id: int):
    a = _get_assignment(assignment_id)
    if not a:
        flash("Tarefa inexistente.", "danger")
        return redirect(url_for("courses.list_courses"))
    user_id = g.user["id"]
    if not _is_member(user_id, a["course_id"]):
        flash("Apenas alunos matriculados podem enviar.", "danger")
        return redirect(url_for("assignments.detail", assignment_id=assignment_id))

    text = (request.form.get("text") or "").strip()
    file = request.files.get("attachment")

    # Se houver arquivo, validar e salvar
    rel_path = None
    if file and file.filename:
        filename = secure_filename(file.filename)
        if not _allowed_file(filename):
            flash("Extensão de arquivo não permitida.", "danger")
            return redirect(url_for("assignments.detail", assignment_id=assignment_id))
        dest_dir = _uploads_dir(a["course_id"])
        final_name = f"assign_{assignment_id}__u_{user_id}__{filename}"
        dest_path = dest_dir / final_name
        file.save(dest_path)
        rel_path = dest_path.relative_to(Path(current_app.config["UPLOAD_FOLDER"]))

    # Se já existe submissão, atualiza; senão cria
    existing = query("SELECT id, attachment_path FROM submissions WHERE assignment_id=? AND student_id=?",
                     (assignment_id, user_id), one=True)
    if existing:
        # remover anexo anterior se trocou
        if rel_path and existing["attachment_path"]:
            old = Path(current_app.config["UPLOAD_FOLDER"]) / existing["attachment_path"]
            if old.exists() and _is_under_uploads(old):
                try: old.unlink()
                except Exception: current_app.logger.warning("Falha ao apagar anexo antigo: %s", old)
        execute("""
            UPDATE submissions
               SET text=?, attachment_path=COALESCE(?, attachment_path), submitted_at=CURRENT_TIMESTAMP
             WHERE id=?
        """, (text or None, str(rel_path) if rel_path else None, existing["id"]))
        flash("Envio atualizado.", "success")
    else:
        execute("""
            INSERT INTO submissions(assignment_id, student_id, text, attachment_path)
            VALUES (?,?,?,?)
        """, (assignment_id, user_id, text or None, str(rel_path) if rel_path else None))
        flash("Envio realizado.", "success")

    return redirect(url_for("assignments.detail", assignment_id=assignment_id))

@bp.get("/download/<int:submission_id>")
@login_required
def download(submission_id: int):
    s = query("""
        SELECT s.*, a.course_id
        FROM submissions s JOIN assignments a ON a.id = s.assignment_id
        WHERE s.id = ?
    """, (submission_id,), one=True)
    if not s or not s["attachment_path"]:
        abort(404)
    user_id = g.user["id"]
    if not (_is_instructor(user_id, s["course_id"]) or user_id == s["student_id"]):
        abort(403)
    abs_path = Path(current_app.config["UPLOAD_FOLDER"]) / s["attachment_path"]
    if not abs_path.exists() or not _is_under_uploads(abs_path):
        abort(404)
    return send_from_directory(abs_path.parent, abs_path.name, as_attachment=True)

@bp.post("/<int:assignment_id>/grade/<int:student_id>")
@login_required
@csrf_protect
def grade(assignment_id: int, student_id: int):
    a = _get_assignment(assignment_id)
    if not a:
        flash("Tarefa inexistente.", "danger"); return redirect(url_for("courses.list_courses"))
    if not _is_instructor(g.user["id"], a["course_id"]):
        flash("Apenas instrutores podem lançar notas.", "danger")
        return redirect(url_for("assignments.detail", assignment_id=assignment_id))

    # Conferir que existe submissão
    sub = query("SELECT id FROM submissions WHERE assignment_id=? AND student_id=?",
                (assignment_id, student_id), one=True)
    if not sub:
        flash("Não há envio deste aluno para avaliar.", "warning")
        return redirect(url_for("assignments.detail", assignment_id=assignment_id))

    # Ler nota/feedback
    raw_grade = (request.form.get("grade") or "").strip()
    feedback = (request.form.get("feedback") or "").strip() or None
    grade_val = None
    if raw_grade != "":
        try:
            grade_val = float(raw_grade)
        except ValueError:
            flash("Nota inválida.", "danger")
            return redirect(url_for("assignments.detail", assignment_id=assignment_id))

    execute("""
        UPDATE submissions
           SET grade=?, feedback=?, graded_at=CURRENT_TIMESTAMP
         WHERE id=?
    """, (grade_val, feedback, sub["id"]))
    flash("Nota/feedback salvos.", "success")
    return redirect(url_for("assignments.detail", assignment_id=assignment_id))

@bp.get("/grades/<int:course_id>")
@login_required
def my_grades(course_id: int):
    if not (_is_member(g.user["id"], course_id) or _is_instructor(g.user["id"], course_id)):
        flash("Você não tem acesso a este boletim.", "danger")
        return redirect(url_for("courses.detail", course_id=course_id))
    rows = query("""
        SELECT a.id AS assignment_id, a.title,
               s.grade, s.feedback, s.submitted_at, s.graded_at
        FROM assignments a
        LEFT JOIN submissions s
               ON s.assignment_id = a.id AND s.student_id = ?
        WHERE a.course_id = ?
        ORDER BY a.created_at
    """, (g.user["id"], course_id))
    # média simples das notas existentes
    grades = [r["grade"] for r in rows if r["grade"] is not None]
    avg = sum(grades)/len(grades) if grades else None
    return render_template("assignments/grades.html", course_id=course_id, rows=rows, avg=avg)