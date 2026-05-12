"""
Student routes - Espace Etudiant
"""
import base64
import json
import os
from datetime import datetime, timezone
from functools import wraps
from flask import render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from werkzeug.utils import secure_filename
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
    profile_picture_url = None
    if student.profile_picture:
        if student.profile_picture.startswith("data:image/"):
            profile_picture_url = student.profile_picture
        else:
            profile_picture_url = url_for("static", filename=student.profile_picture)
    if not profile_picture_url:
        flash("Veuillez d'abord televerser votre photo d'identite.", "warning")
        return redirect(url_for("student.profile"))
    face_descriptor = []
    if student.face_descriptor:
        try:
            face_descriptor = json.loads(student.face_descriptor)
        except (TypeError, ValueError):
            face_descriptor = []
    has_face_profile = len(face_descriptor) == 128
    return render_template("student/scanner.html", 
                           student=student, 
                           has_face_profile=has_face_profile,
                           face_descriptor=face_descriptor,
                           profile_picture_url=profile_picture_url)


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
        photo = request.files.get("id_photo")
        if photo and photo.filename:
            filename = secure_filename(photo.filename)
            ext = os.path.splitext(filename)[1].lower()
            if ext not in {".jpg", ".jpeg", ".png"}:
                flash("Format photo invalide. Utilisez JPG ou PNG.", "error")
                return redirect(url_for("student.profile"))
            max_bytes = current_app.config.get("ID_PHOTO_MAX_BYTES", 2_500_000)
            photo_bytes = photo.read()
            if len(photo_bytes) > max_bytes:
                flash("Photo trop grande. Max 2.5MB.", "error")
                return redirect(url_for("student.profile"))
            mime = photo.mimetype if photo.mimetype in {"image/jpeg", "image/png"} else "image/jpeg"
            encoded = base64.b64encode(photo_bytes).decode("utf-8")
            student.profile_picture = f"data:{mime};base64,{encoded}"
            student.face_descriptor = None
        db.session.commit()
        flash("Profil mis a jour.", "success")
        return redirect(url_for("student.profile"))
    profile_picture_url = None
    if student.profile_picture:
        if student.profile_picture.startswith("data:image/"):
            profile_picture_url = student.profile_picture
        else:
            profile_picture_url = url_for("static", filename=student.profile_picture)
    return render_template("student/profile.html", student=student, profile_picture_url=profile_picture_url)
