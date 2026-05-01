"""
Auth routes - Inscription, Connexion, Reset mot de passe
"""
from datetime import datetime, timezone
from flask import (render_template, request, redirect, url_for,
                   flash, jsonify, current_app)
from flask_jwt_extended import (create_access_token, create_refresh_token,
                                 jwt_required, get_jwt_identity, get_jwt,
                                 set_access_cookies, set_refresh_cookies,
                                 unset_jwt_cookies)
from app import db, limiter
from app.auth import bp
from app.models.user import User
from app.models.token import RevokedToken, PasswordResetToken
from app.models.audit import AuditLog
from app.services.email_service import (send_confirmation_email,
                                         send_password_reset_email)


# ── Inscription Professeur ─────────────────────────────────────────────────
@bp.route("/inscription", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("auth/register.html")

    data = request.get_json() if request.is_json else request.form

    # Validation
    required = ["first_name", "last_name", "email", "password", "department"]
    for field in required:
        if not data.get(field, "").strip():
            msg = f"Le champ {field} est requis."
            if request.is_json:
                return jsonify({"success": False, "error": msg}), 400
            flash(msg, "error")
            return redirect(url_for("auth.register"))

    email = data["email"].strip().lower()
    if User.query.filter_by(email=email).first():
        msg = "Un compte avec cet email existe déjà."
        if request.is_json:
            return jsonify({"success": False, "error": msg}), 409
        flash(msg, "error")
        return redirect(url_for("auth.register"))

    # Création du compte professeur
    confirm_token = User.generate_confirm_token()
    user = User(
        first_name=data["first_name"].strip(),
        last_name=data["last_name"].strip(),
        email=email,
        phone=data.get("phone", "").strip(),
        role="professor",
        university=data.get("university", "Université Euro-Méditerranéenne de Fès").strip(),
        department=data["department"].strip(),
        is_active=False,
        email_confirmed=False,
        email_confirm_token=confirm_token,
    )
    user.set_password(data["password"])

    db.session.add(user)

    # Audit
    AuditLog.log("REGISTER", user_id=user.id, resource_type="user",
                 ip_address=request.remote_addr, user_agent=request.user_agent.string)
    db.session.commit()

    # Email de confirmation
    confirm_url = url_for("auth.confirm_email", token=confirm_token, _external=True)
    email_sent = send_confirmation_email(user, confirm_url)
    
    if not email_sent:
        user.is_active = True
        user.email_confirmed = True
        db.session.commit()
        msg = "Compte créé et activé automatiquement (L'envoi d'email n'est pas configuré)."
    else:
        msg = "Compte créé ! Veuillez vérifier votre email pour l'activer."

    if request.is_json:
        return jsonify({"success": True, "message": msg}), 201
    flash(msg, "success")
    return redirect(url_for("auth.login"))


# ── Confirmation email ─────────────────────────────────────────────────────
@bp.route("/confirmer/<token>")
def confirm_email(token):
    user = User.query.filter_by(email_confirm_token=token).first()
    if not user:
        flash("Lien de confirmation invalide ou expiré.", "error")
        return redirect(url_for("auth.login"))

    user.email_confirmed = True
    user.is_active = True
    user.email_confirm_token = None
    AuditLog.log("EMAIL_CONFIRMED", user_id=user.id, ip_address=request.remote_addr)
    db.session.commit()

    flash("Email confirmé ! Vous pouvez maintenant vous connecter.", "success")
    return redirect(url_for("auth.login"))


# ── Connexion ──────────────────────────────────────────────────────────────
@bp.route("/connexion", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def login():
    if request.method == "GET":
        return render_template("auth/login.html")

    data = request.get_json() if request.is_json else request.form
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    user = User.query.filter_by(email=email).first()

    def fail(msg, code=401):
        AuditLog.log("LOGIN_FAILED", ip_address=request.remote_addr,
                     extra_data={"email": email, "reason": msg}, success=False)
        db.session.commit()
        if request.is_json:
            return jsonify({"success": False, "error": msg}), code
        flash(msg, "error")
        return redirect(url_for("auth.login"))

    if not user:
        return fail("Email ou mot de passe incorrect.")

    if user.is_locked:
        return fail("Compte temporairement bloqué. Réessayez dans quelques minutes.")

    if not user.check_password(password):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= current_app.config["MAX_LOGIN_ATTEMPTS"]:
            from datetime import timedelta
            user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
            db.session.commit()
            return fail("Trop de tentatives. Compte bloqué 15 minutes.")
        db.session.commit()
        return fail("Email ou mot de passe incorrect.")

    if not user.is_active and not user.is_temp_password:
        return fail("Compte inactif. Vérifiez votre email pour l'activer.")

    # Succès
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login = datetime.now(timezone.utc)
    AuditLog.log("LOGIN", user_id=user.id, ip_address=request.remote_addr,
                 user_agent=request.user_agent.string)
    db.session.commit()

    # JWT
    additional_claims = {"role": user.role, "email": user.email}
    access_token = create_access_token(identity=user.id, additional_claims=additional_claims)
    refresh_token = create_refresh_token(identity=user.id)

    # Redirection selon rôle
    if user.role == "professor":
        redirect_url = url_for("professor.dashboard")
    else:
        redirect_url = url_for("student.profile") if user.is_temp_password else url_for("student.dashboard")

    if request.is_json:
        return jsonify({
            "success": True,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "role": user.role,
            "redirect": redirect_url,
            "is_temp_password": user.is_temp_password,
        })

    response = redirect(redirect_url)
    set_access_cookies(response, access_token)
    set_refresh_cookies(response, refresh_token)
    return response


# ── Déconnexion ────────────────────────────────────────────────────────────
@bp.route("/deconnexion", methods=["GET", "POST"])
@jwt_required(locations=["cookies", "headers"])
def logout():
    jti = get_jwt()["jti"]
    user_id = get_jwt_identity()
    RevokedToken.revoke(jti)
    AuditLog.log("LOGOUT", user_id=user_id, ip_address=request.remote_addr)
    db.session.commit()

    response = redirect(url_for("auth.login"))
    unset_jwt_cookies(response)
    flash("Déconnexion réussie.", "success")
    return response


# ── Mot de passe oublié ────────────────────────────────────────────────────
@bp.route("/mot-de-passe-oublie", methods=["GET", "POST"])
@limiter.limit("3 per minute", methods=["POST"])
def forgot_password():
    if request.method == "GET":
        return render_template("auth/forgot_password.html")

    data = request.get_json() if request.is_json else request.form
    email = data.get("email", "").strip().lower()
    user = User.query.filter_by(email=email).first()

    # Toujours répondre de la même façon (anti-enumération)
    msg = "Si cet email est enregistré, vous recevrez un lien de réinitialisation."

    if user and user.is_active:
        token_obj = PasswordResetToken.create_for_user(
            user.id,
            current_app.config["PASSWORD_RESET_EXPIRY_MINUTES"]
        )
        reset_url = url_for("auth.reset_password", token=token_obj.token, _external=True)
        email_sent = send_password_reset_email(user, reset_url)
        AuditLog.log("PASSWORD_RESET_REQUEST", user_id=user.id,
                     ip_address=request.remote_addr)
        db.session.commit()
        
        if not email_sent:
            msg = f"Email non configuré. Lien de réinitialisation (Dev): {reset_url}"

    if request.is_json:
        return jsonify({"success": True, "message": msg})
    flash(msg, "info")
    return redirect(url_for("auth.login"))


# ── Reset mot de passe ─────────────────────────────────────────────────────
@bp.route("/reinitialiser/<token>", methods=["GET", "POST"])
def reset_password(token):
    token_obj = PasswordResetToken.query.filter_by(token=token).first()

    if not token_obj or not token_obj.is_valid:
        flash("Lien expiré ou invalide. Veuillez refaire une demande.", "error")
        return redirect(url_for("auth.forgot_password"))

    if request.method == "GET":
        return render_template("auth/reset_password.html", token=token)

    data = request.get_json() if request.is_json else request.form
    new_password = data.get("password", "")
    confirm = data.get("confirm_password", "")

    if len(new_password) < 8:
        msg = "Le mot de passe doit contenir au moins 8 caractères."
        if request.is_json:
            return jsonify({"success": False, "error": msg}), 400
        flash(msg, "error")
        return redirect(request.url)

    if new_password != confirm:
        msg = "Les mots de passe ne correspondent pas."
        if request.is_json:
            return jsonify({"success": False, "error": msg}), 400
        flash(msg, "error")
        return redirect(request.url)

    user = token_obj.user
    user.set_password(new_password)
    user.is_temp_password = False
    user.is_active = True
    token_obj.used = True

    AuditLog.log("PASSWORD_RESET", user_id=user.id, ip_address=request.remote_addr)
    db.session.commit()

    if request.is_json:
        return jsonify({"success": True, "message": "Mot de passe réinitialisé avec succès."})
    flash("Mot de passe réinitialisé ! Vous pouvez vous connecter.", "success")
    return redirect(url_for("auth.login"))


# ── Refresh token ──────────────────────────────────────────────────────────
@bp.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh():
    identity = get_jwt_identity()
    user = User.query.get(identity)
    if not user:
        return jsonify({"error": "Utilisateur introuvable"}), 404
    access_token = create_access_token(
        identity=identity,
        additional_claims={"role": user.role, "email": user.email}
    )
    return jsonify({"access_token": access_token})
