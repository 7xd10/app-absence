"""
Student routes - Espace Étudiant
"""
from datetime import datetime, timezone
from functools import wraps
from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from app import db
from app.student import bp
from app.models.user import User
from app.models.session import Session, Attendance
from app.models.group import GroupStudent
from app.models.message import Message
from app.models.audit import AuditLog


def student_required(f):
    @wraps(f)
    @jwt_required(locations=["cookies", "headers"])
    def decorated(*args, **kwargs):
        claims = get_jwt()
        if claims.get("role") != "student":
            flash("Accès réservé aux étudiants.", "error")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


@bp.route("/dashboard")
@student_required
def dashboard():
    student_id = get_jwt_identity()
    student = User.query.get_or_404(student_id)
    attendances = Attendance.query.filter_by(student_id=student_id)\
        .order_by(Attendance.created_at.desc()).all()
    total = len(attendances)
    present = sum(1 for a in attendances if a.status == "present")
    rate = round(present / max(total, 1) * 100, 1)
    recent = attendances[:10]
    messages = Message.query.filter_by(recipient_id=student_id, is_read=False).count()
    return render_template("student/dashboard.html",
                           student=student, attendances=recent,
                           total=total, present=present,
                           absent=total - present, rate=rate,
                           unread_messages=messages)


@bp.route("/scanner")
@student_required
def scanner():
    student_id = get_jwt_identity()
    student = User.query.get_or_404(student_id)
    if student.is_temp_password:
        flash("Veuillez d'abord changer votre mot de passe temporaire.", "warning")
        return redirect(url_for("student.profile"))
    return render_template("student/scanner.html", student=student)


@bp.route("/historique")
@student_required
def history():
    student_id = get_jwt_identity()
    attendances = Attendance.query.filter_by(student_id=student_id)\
        .order_by(Attendance.created_at.desc()).all()
    return render_template("student/history.html", attendances=attendances)


@bp.route("/messages")
@student_required
def messages():
    student_id = get_jwt_identity()
    msgs = Message.query.filter_by(recipient_id=student_id)\
        .order_by(Message.created_at.desc()).all()
    # Marquer comme lus
    for m in msgs:
        m.is_read = True
    db.session.commit()
    return render_template("student/messages.html", messages=msgs)


@bp.route("/profil", methods=["GET", "POST"])
@student_required
def profile():
    student_id = get_jwt_identity()
    student = User.query.get_or_404(student_id)
    if request.method == "POST":
        data = request.form
        student.first_name = data.get("first_name", student.first_name).strip()
        student.last_name = data.get("last_name", student.last_name).strip()
        student.phone = data.get("phone", student.phone or "").strip()
        if data.get("new_password"):
            if not student.check_password(data.get("current_password", "")):
                flash("Mot de passe actuel incorrect.", "error")
                return redirect(url_for("student.profile"))
            student.set_password(data["new_password"])
            student.is_temp_password = False
            student.is_active = True
            student.temp_password_plain = None
            student.temp_password_expires_at = None
        db.session.commit()
        flash("Profil mis à jour.", "success")
        return redirect(url_for("student.profile"))
    return render_template("student/profile.html", student=student)
