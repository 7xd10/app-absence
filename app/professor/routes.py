"""
Professor routes - Espace Professeur complet
"""
from datetime import datetime, timezone
from flask import (render_template, request, redirect, url_for,
                   flash, jsonify, current_app, send_file)
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from functools import wraps
from app import db, limiter
from app.professor import bp
from app.models.user import User
from app.models.group import Group, GroupStudent
from app.models.session import Session, Attendance, session_groups_table
from app.models.message import Message
from app.models.audit import AuditLog
from app.utils.network import get_client_ip


def professor_required(f):
    """Décorateur : accès réservé aux professeurs."""
    @wraps(f)
    @jwt_required(locations=["cookies", "headers"])
    def decorated(*args, **kwargs):
        claims = get_jwt()
        if claims.get("role") != "professor":
            flash("Accès réservé aux professeurs.", "error")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


# ── Dashboard ──────────────────────────────────────────────────────────────
@bp.route("/dashboard")
@professor_required
def dashboard():
    prof_id = get_jwt_identity()
    prof = User.query.get_or_404(prof_id)
    groups = Group.query.filter_by(professor_id=prof_id, is_active=True).all()
    total_students = sum(g.student_count for g in groups)
    today = datetime.now(timezone.utc).date()
    sessions_today = Session.query.filter(
        Session.professor_id == prof_id,
        db.func.date(Session.scheduled_at) == today
    ).count()
    # Taux global
    all_att = Attendance.query.join(Session).filter(Session.professor_id == prof_id)
    total_att = all_att.count()
    present_att = all_att.filter(Attendance.status == "present").count()
    global_rate = round(present_att / max(total_att, 1) * 100, 1)

    recent_sessions = Session.query.filter_by(professor_id=prof_id)\
        .order_by(Session.created_at.desc()).limit(5).all()

    return render_template("professor/dashboard.html",
                           prof=prof, groups=groups,
                           total_students=total_students,
                           sessions_today=sessions_today,
                           global_rate=global_rate,
                           recent_sessions=recent_sessions)


# ── Groupes ────────────────────────────────────────────────────────────────
@bp.route("/groupes")
@professor_required
def groups():
    prof_id = get_jwt_identity()
    groups = Group.query.filter_by(professor_id=prof_id, is_active=True)\
        .order_by(Group.created_at.desc()).all()
    return render_template("professor/groups.html", groups=groups)


@bp.route("/groupes/nouveau", methods=["GET", "POST"])
@professor_required
def new_group():
    prof_id = get_jwt_identity()
    if request.method == "POST":
        data = request.form
        g = Group(
            name=data["name"].strip(),
            filiere=data.get("filiere", "").strip(),
            level=data.get("level", "").strip(),
            academic_year=data.get("academic_year", "").strip(),
            description=data.get("description", "").strip(),
            professor_id=prof_id,
        )
        db.session.add(g)
        AuditLog.log("GROUP_CREATE", user_id=prof_id, resource_type="group")
        db.session.commit()
        flash(f"Groupe « {g.name} » créé avec succès.", "success")
        return redirect(url_for("professor.group_detail", group_id=g.id))
    return render_template("professor/group_form.html", group=None)


@bp.route("/groupes/<group_id>")
@professor_required
def group_detail(group_id):
    prof_id = get_jwt_identity()
    group = Group.query.filter_by(id=group_id, professor_id=prof_id).first_or_404()
    memberships = GroupStudent.query.filter_by(group_id=group_id, is_active=True).all()
    students = [m.student for m in memberships]
    return render_template("professor/group_detail.html", group=group, students=students, now=datetime.now(timezone.utc).replace(tzinfo=None))


@bp.route("/groupes/<group_id>/ajouter-etudiant", methods=["POST"])
@professor_required
def add_student(group_id):
    prof_id = get_jwt_identity()
    group = Group.query.filter_by(id=group_id, professor_id=prof_id).first_or_404()
    data = request.form

    email = data.get("email", "").strip().lower()
    existing = User.query.filter_by(email=email).first()

    if existing:
        # Vérifier s'il est déjà dans le groupe (actif ou supprimé)
        membership = GroupStudent.query.filter_by(group_id=group_id, student_id=existing.id).first()
        student = existing
        temp_pwd = None
        
        if membership:
            if membership.is_active:
                flash("Cet étudiant est déjà dans le groupe.", "warning")
                return redirect(url_for("professor.group_detail", group_id=group_id))
            else:
                # L'étudiant avait été retiré : on le réactive
                membership.is_active = True
                # Règle README : retirer et ré-ajouter = génération d'un nouveau mot de passe
                temp_pwd = User.generate_temp_password()
                student.set_password(temp_pwd)
                student.is_temp_password = True
                student.is_active = False
        else:
            # L'étudiant existe mais n'était pas dans ce groupe
            membership = GroupStudent(group_id=group_id, student_id=student.id)
            db.session.add(membership)
            # On ne réinitialise son mot de passe que s'il n'avait pas encore activé son compte
            if student.is_temp_password or not student.is_active:
                temp_pwd = User.generate_temp_password()
                student.set_password(temp_pwd)
                student.is_temp_password = True
                student.is_active = False
    else:
        # Créer un nouveau compte étudiant
        temp_pwd = User.generate_temp_password()
        student = User(
            first_name=data.get("first_name", "").strip(),
            last_name=data.get("last_name", "").strip(),
            email=email,
            matricule=data.get("matricule", "").strip() or None,
            role="student",
            is_active=False,
            is_temp_password=True,
            email_confirmed=True,
        )
        student.set_password(temp_pwd)
        db.session.add(student)
        db.session.flush()
        membership = GroupStudent(group_id=group_id, student_id=student.id)
        db.session.add(membership)

    if temp_pwd:
        from datetime import timedelta
        student.temp_password_plain = temp_pwd
        student.temp_password_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        
        from app.services.email_service import send_temp_password_email
        login_url = url_for("auth.login", _external=True)
        email_sent = send_temp_password_email(student, temp_pwd, login_url)
        if not email_sent:
            AuditLog.log("STUDENT_ADD", user_id=prof_id, resource_type="user", resource_id=student.id)
            db.session.commit()
            flash(f"Étudiant {student.full_name} ajouté. Mdp provisoire : {temp_pwd} (Email non envoyé)", "warning")
            return redirect(url_for("professor.group_detail", group_id=group_id))

    AuditLog.log("STUDENT_ADD", user_id=prof_id, resource_type="user", resource_id=student.id)
    db.session.commit()
    flash(f"Étudiant {student.full_name} ajouté avec succès.", "success")
    return redirect(url_for("professor.group_detail", group_id=group_id))


@bp.route("/groupes/<group_id>/importer", methods=["POST"])
@professor_required
def import_students(group_id):
    """Import CSV/Excel d'étudiants."""
    prof_id = get_jwt_identity()
    group = Group.query.filter_by(id=group_id, professor_id=prof_id).first_or_404()

    file = request.files.get("file")
    if not file:
        flash("Aucun fichier sélectionné.", "error")
        return redirect(url_for("professor.group_detail", group_id=group_id))

    filename = file.filename.lower()
    created, skipped = 0, 0

    try:
        from datetime import timedelta
        if filename.endswith(".csv"):
            import csv, io
            content = file.read().decode("utf-8-sig")
            # Tente de détecter le délimiteur
            sniffer = csv.Sniffer()
            try:
                dialect = sniffer.sniff(content[:1024])
                delimiter = dialect.delimiter
            except:
                delimiter = ";" if ";" in content[:100] else ","
            reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
            rows = list(reader)
        else:
            import pandas as pd
            df = pd.read_excel(file)
            rows = df.to_dict("records")

        if not rows:
            flash("Le fichier est vide ou mal formaté.", "warning")
            return redirect(url_for("professor.group_detail", group_id=group_id))

        for row in rows:
            # Cherche la colonne email
            email_key = next((k for k in row.keys() if k and "email" in str(k).lower()), None)
            if not email_key:
                continue
            email = str(row.get(email_key, "")).strip().lower()
            if not email:
                continue

            existing = User.query.filter_by(email=email).first()
            if existing:
                if not GroupStudent.query.filter_by(group_id=group_id, student_id=existing.id).first():
                    db.session.add(GroupStudent(group_id=group_id, student_id=existing.id))
                    created += 1
                else:
                    skipped += 1
                continue

            # Cherche prénom, nom, matricule avec tolérance
            first_key = next((k for k in row.keys() if k and ("prenom" in str(k).lower() or "first" in str(k).lower())), None)
            last_key = next((k for k in row.keys() if k and ("nom" in str(k).lower() or "last" in str(k).lower())), None)
            mat_key = next((k for k in row.keys() if k and "matricule" in str(k).lower()), None)

            first_name = str(row.get(first_key, "")) if first_key else ""
            last_name = str(row.get(last_key, "")) if last_key else ""
            matricule = str(row.get(mat_key, "")) if mat_key else None

            temp_pwd = User.generate_temp_password()
            student = User(
                first_name=first_name.strip() or "Prénom",
                last_name=last_name.strip() or "Nom",
                email=email,
                matricule=matricule.strip() if matricule else None,
                role="student",
                is_active=False,
                is_temp_password=True,
                email_confirmed=True,
                temp_password_plain=temp_pwd,
                temp_password_expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
            )
            student.set_password(temp_pwd)
            db.session.add(student)
            db.session.flush()
            db.session.add(GroupStudent(group_id=group_id, student_id=student.id))

            from app.services.email_service import send_temp_password_email
            email_sent = send_temp_password_email(student, temp_pwd, url_for("auth.login", _external=True))
            if not email_sent:
                current_app.logger.warning(f"Email failed for {student.email}. Temp pwd: {temp_pwd}")
            created += 1

        db.session.commit()
        flash(f"{created} étudiant(s) importé(s), {skipped} ignoré(s).", "success")
    except Exception as e:
        db.session.rollback()
        import traceback
        err_msg = f"Erreur lors de l'import : {str(e)}"
        current_app.logger.error(f"{err_msg}\n{traceback.format_exc()}")
        AuditLog.log("IMPORT_ERROR", user_id=prof_id, resource_type="group", resource_id=group_id, 
                     extra_data={"error": str(e), "trace": traceback.format_exc()}, success=False)
        db.session.commit()
        flash(err_msg, "error")

    return redirect(url_for("professor.group_detail", group_id=group_id))


@bp.route("/groupes/<group_id>/supprimer-etudiant/<student_id>", methods=["POST"])
@professor_required
def remove_student(group_id, student_id):
    prof_id = get_jwt_identity()
    group = Group.query.filter_by(id=group_id, professor_id=prof_id).first_or_404()
    membership = GroupStudent.query.filter_by(group_id=group_id, student_id=student_id).first_or_404()
    membership.is_active = False
    AuditLog.log("STUDENT_REMOVE", user_id=prof_id, resource_id=student_id)
    db.session.commit()
    flash("Étudiant retiré du groupe.", "success")
    return redirect(url_for("professor.group_detail", group_id=group_id))


# ── Sessions ───────────────────────────────────────────────────────────────
@bp.route("/seances")
@professor_required
def sessions():
    prof_id = get_jwt_identity()
    sessions = Session.query.filter_by(professor_id=prof_id)\
        .order_by(Session.created_at.desc()).all()
    groups = Group.query.filter_by(professor_id=prof_id, is_active=True).all()
    return render_template("professor/sessions.html", sessions=sessions, groups=groups)


@bp.route("/seances/nouvelle", methods=["POST"])
@professor_required
def new_session():
    prof_id = get_jwt_identity()
    data = request.form
    session = Session(
        title=data["title"].strip(),
        room=data.get("room", "").strip(),
        session_type=data.get("session_type", "punctual"),
        professor_id=prof_id,
        duration_minutes=int(data.get("duration", 90)),
        scheduled_at=datetime.fromisoformat(data["scheduled_at"]) if data.get("scheduled_at") else None,
    )
    db.session.add(session)
    db.session.flush()

    group_ids = request.form.getlist("group_ids")
    for gid in group_ids:
        g = Group.query.filter_by(id=gid, professor_id=prof_id).first()
        if g:
            db.session.execute(session_groups_table.insert().values(
                session_id=session.id, group_id=gid))

    AuditLog.log("SESSION_CREATE", user_id=prof_id, resource_type="session", resource_id=session.id)
    db.session.commit()
    flash(f"Séance « {session.title} » créée.", "success")
    return redirect(url_for("professor.sessions"))


@bp.route("/seances/<session_id>/supprimer", methods=["POST"])
@professor_required
def delete_session(session_id):
    prof_id = get_jwt_identity()
    session = Session.query.filter_by(id=session_id, professor_id=prof_id).first_or_404()
    
    AuditLog.log("SESSION_DELETE", user_id=prof_id, resource_type="session", resource_id=session.id)
    
    db.session.delete(session)
    db.session.commit()
    
    flash(f"Séance « {session.title} » supprimée définitivement.", "success")
    return redirect(url_for("professor.sessions"))


# ── Gestion présences / QR ─────────────────────────────────────────────────
@bp.route("/presence/<session_id>")
@professor_required
def attendance_session(session_id):
    prof_id = get_jwt_identity()
    session = Session.query.filter_by(id=session_id, professor_id=prof_id).first_or_404()
    groups = list(session.groups)
    return render_template("professor/attendance_session.html",
                           session=session, groups=groups)


@bp.route("/presence/<session_id>/demarrer", methods=["POST"])
@professor_required
def start_session(session_id):
    prof_id = get_jwt_identity()
    session = Session.query.filter_by(id=session_id, professor_id=prof_id).first_or_404()

    data = request.get_json() or {}
    session.status = "active"
    session.started_at = datetime.now(timezone.utc)
    session.professor_lat = data.get("lat")
    session.professor_lng = data.get("lng")
    session.professor_ip = get_client_ip()

    # Initialiser les présences à "absent" pour tous les étudiants
    for group in session.groups:
        for membership in group.members.filter_by(is_active=True):
            existing = Attendance.query.filter_by(
                session_id=session.id, student_id=membership.student_id).first()
            if not existing:
                att = Attendance(
                    session_id=session.id,
                    student_id=membership.student_id,
                    group_id=group.id,
                    status="absent",
                )
                db.session.add(att)

    AuditLog.log("SESSION_START", user_id=prof_id, resource_type="session", resource_id=session.id)
    db.session.commit()
    return jsonify({"success": True, "session_id": session.id})


@bp.route("/presence/<session_id>/terminer", methods=["POST"])
@professor_required
def end_session(session_id):
    prof_id = get_jwt_identity()
    session = Session.query.filter_by(id=session_id, professor_id=prof_id).first_or_404()
    session.status = "ended"
    session.ended_at = datetime.now(timezone.utc)
    AuditLog.log("SESSION_END", user_id=prof_id, resource_type="session", resource_id=session.id)
    db.session.commit()
    return jsonify({"success": True})


# ── Export ─────────────────────────────────────────────────────────────────
@bp.route("/presence/<session_id>/export/<fmt>")
@professor_required
def export_session(session_id, fmt):
    prof_id = get_jwt_identity()
    session = Session.query.filter_by(id=session_id, professor_id=prof_id).first_or_404()
    attendances = Attendance.query.filter_by(session_id=session_id)\
        .order_by(Attendance.status.desc()).all()

    from app.services.export_service import (export_attendance_excel,
                                              export_attendance_csv,
                                              export_attendance_pdf)
    import io
    safe_title = "".join(c for c in session.title if c.isalnum() or c in " _-")[:40]

    if fmt == "excel":
        data = export_attendance_excel(session, attendances)
        return send_file(io.BytesIO(data), download_name=f"presences_{safe_title}.xlsx",
                         as_attachment=True, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    elif fmt == "csv":
        data = export_attendance_csv(session, attendances)
        return send_file(io.BytesIO(data), download_name=f"presences_{safe_title}.csv",
                         as_attachment=True, mimetype="text/csv")
    elif fmt == "pdf":
        data = export_attendance_pdf(session, attendances)
        return send_file(io.BytesIO(data), download_name=f"presences_{safe_title}.pdf",
                         as_attachment=True, mimetype="application/pdf")

    flash("Format d'export inconnu.", "error")
    return redirect(url_for("professor.sessions"))


# ── Messages ───────────────────────────────────────────────────────────────
@bp.route("/messages")
@professor_required
def messages():
    prof_id = get_jwt_identity()
    msgs = Message.query.filter_by(sender_id=prof_id)\
        .order_by(Message.created_at.desc()).all()
    groups = Group.query.filter_by(professor_id=prof_id, is_active=True).all()
    return render_template("professor/messages.html", messages=msgs, groups=groups)


@bp.route("/messages/envoyer", methods=["POST"])
@professor_required
def send_message():
    prof_id = get_jwt_identity()
    data = request.form
    body = data.get("body", "").strip()
    subject = data.get("subject", "Message EuroPresence").strip()
    msg_type = data.get("message_type", "info")
    send_email = data.get("send_email") == "on"
    group_id = data.get("group_id")
    student_id = data.get("student_id")

    recipients = []
    if group_id:
        group = Group.query.filter_by(id=group_id, professor_id=prof_id).first_or_404()
        recipients = [m.student for m in group.members.filter_by(is_active=True)]
    elif student_id:
        s = User.query.filter_by(id=student_id, role="student").first_or_404()
        recipients = [s]

    prof = User.query.get(prof_id)
    for recipient in recipients:
        msg = Message(sender_id=prof_id, recipient_id=recipient.id,
                      group_id=group_id, subject=subject, body=body,
                      message_type=msg_type)
        db.session.add(msg)
        if send_email:
            from app.services.email_service import send_warning_email
            send_warning_email(recipient, prof.full_name, subject, body)
            msg.is_email_sent = True

    db.session.commit()
    flash(f"Message envoyé à {len(recipients)} destinataire(s).", "success")
    return redirect(url_for("professor.messages"))


# ── Profil ─────────────────────────────────────────────────────────────────
@bp.route("/profil", methods=["GET", "POST"])
@professor_required
def profile():
    prof_id = get_jwt_identity()
    prof = User.query.get_or_404(prof_id)
    if request.method == "POST":
        data = request.form
        prof.first_name = data.get("first_name", prof.first_name).strip()
        prof.last_name = data.get("last_name", prof.last_name).strip()
        prof.phone = data.get("phone", prof.phone).strip()
        prof.department = data.get("department", prof.department).strip()
        if data.get("new_password"):
            if not prof.check_password(data.get("current_password", "")):
                flash("Mot de passe actuel incorrect.", "error")
                return redirect(url_for("professor.profile"))
            prof.set_password(data["new_password"])
        db.session.commit()
        flash("Profil mis à jour.", "success")
        return redirect(url_for("professor.profile"))
    return render_template("professor/profile.html", prof=prof)
