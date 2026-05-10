"""
API routes - REST API pour le QR code, les présences, et les stats
"""
import math
from datetime import datetime, timezone
from flask import jsonify, request, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from app import db, limiter
from app.api import bp
from app.models.user import User
from app.models.session import Session, Attendance
from app.models.group import Group, GroupStudent
from app.models.device import DeviceFingerprint
from app.models.audit import AuditLog
from app.services.qr_service import generate_qr_base64, validate_scan
from app.utils.network import get_client_ip


def _haversine(lat1, lng1, lat2, lng2) -> float:
    """Distance en mètres entre deux coordonnées GPS."""
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ── QR Code dynamique ──────────────────────────────────────────────────────
@bp.route("/session/<session_id>/qr")
@jwt_required(locations=["cookies", "headers"])
def get_qr(session_id):
    """Retourne le QR code base64 courant (rafraîchi automatiquement)."""
    claims = get_jwt()
    if claims.get("role") != "professor":
        return jsonify({"error": "Accès refusé"}), 403

    prof_id = get_jwt_identity()
    session = Session.query.filter_by(id=session_id, professor_id=prof_id,
                                       status="active").first_or_404()
    qr_b64 = generate_qr_base64(session)
    payload = session.generate_qr_payload()
    rotation = current_app.config.get("QR_ROTATION_SECONDS", 10)

    return jsonify({
        "qr_base64": qr_b64,
        "payload": payload,
        "rotation_seconds": rotation,
        "expires_at": payload["timestamp"] + rotation,
    })


# ── Scan étudiant ──────────────────────────────────────────────────────────
@bp.route("/scan", methods=["POST"])
@jwt_required(locations=["cookies", "headers"])
@limiter.limit("300 per minute")
def scan_qr():
    """Traite le scan QR d'un étudiant avec vérifications anti-fraude."""
    claims = get_jwt()
    if claims.get("role") != "student":
        return jsonify({"success": False, "error": "Accès réservé aux étudiants"}), 403

    student_id = get_jwt_identity()
    student = User.query.get_or_404(student_id)

    if student.is_temp_password:
        return jsonify({"success": False, "error": "Changez d'abord votre mot de passe temporaire"}), 403

    data = request.get_json() or {}
    qr_data = data.get("qr_data", {})
    student_lat = data.get("lat")
    student_lng = data.get("lng")
    fingerprint = data.get("fingerprint", "")
    ip = get_client_ip()
    fraud_flags = []

    # ── Validation QR ──────────────────────────────────────────────────────
    session_id = qr_data.get("session_id")
    session = Session.query.filter_by(id=session_id, status="active").first()
    if not session:
        return jsonify({"success": False, "error": "Session introuvable ou terminée"}), 404

    valid, reason = validate_scan(qr_data, session)
    if not valid:
        AuditLog.log("SCAN_INVALID_QR", user_id=student_id, resource_id=session_id,
                     ip_address=ip, extra_data={"reason": reason}, success=False)
        db.session.commit()
        return jsonify({"success": False, "error": reason}), 400

    # ── Vérifier appartenance au groupe ────────────────────────────────────
    att = Attendance.query.filter_by(session_id=session_id, student_id=student_id).first()
    if not att:
        return jsonify({"success": False, "error": "Vous n'êtes pas inscrit à cette session"}), 403

    if att.status == "present":
        return jsonify({"success": False, "error": "Présence déjà enregistrée"}), 409

    # ── Même Réseau (IP) ───────────────────────────────────────────────────
    if session.professor_ip and ip and ip != session.professor_ip:
        fraud_flags.append(f"WRONG_NETWORK:{ip}")
        att.status = "pending"
        att.fraud_flags = fraud_flags
        att.ip_address = ip
        AuditLog.log("SCAN_WRONG_NETWORK", user_id=student_id, resource_id=session_id,
                     ip_address=ip, success=False)
        db.session.commit()
        return jsonify({
            "success": False,
            "error": "Vous devez être connecté au même réseau Wi-Fi que le professeur pour valider votre présence."
        }), 403

    # ── Géofencing ─────────────────────────────────────────────────────────
    distance = None
    if session.professor_lat and session.professor_lng:
        if student_lat is None or student_lng is None:
            fraud_flags.append("NO_LOCATION")
            att.status = "pending"
            att.fraud_flags = fraud_flags
            AuditLog.log("SCAN_NO_LOCATION", user_id=student_id, resource_id=session_id,
                         ip_address=ip, success=False)
            db.session.commit()
            return jsonify({"success": False, "error": "Localisation requise pour valider la présence"}), 403

        distance = _haversine(session.professor_lat, session.professor_lng,
                               float(student_lat), float(student_lng))
        radius = current_app.config.get("GEOFENCE_RADIUS_METERS", 80)

        if distance > radius:
            fraud_flags.append(f"OUT_OF_GEOFENCE:{distance:.0f}m")
            att.status = "pending"
            att.fraud_flags = fraud_flags
            att.student_lat = float(student_lat)
            att.student_lng = float(student_lng)
            att.distance_meters = distance
            att.ip_address = ip
            AuditLog.log("SCAN_OUT_OF_GEOFENCE", user_id=student_id, resource_id=session_id,
                         ip_address=ip, extra_data={"distance": distance}, success=False)
            db.session.commit()
            return jsonify({
                "success": False,
                "error": f"Trop loin de la salle ({distance:.0f}m). Présence refusée."
            }), 403

    # ── Device fingerprint ─────────────────────────────────────────────────
    if fingerprint:
        existing_device = DeviceFingerprint.query.filter_by(
            user_id=student_id, fingerprint=fingerprint).first()
        if not existing_device:
            # Vérifier s'il y a déjà un autre appareil de confiance
            other_devices = DeviceFingerprint.query.filter_by(
                user_id=student_id, is_trusted=True).count()
            if other_devices > 0:
                fraud_flags.append("NEW_DEVICE")
            new_dev = DeviceFingerprint(
                user_id=student_id,
                fingerprint=fingerprint,
                user_agent=request.user_agent.string,
                ip_address=ip,
            )
            db.session.add(new_dev)
        else:
            existing_device.last_seen = datetime.now(timezone.utc)

    # ── Enregistrement présence ────────────────────────────────────────────
    att.status = "present"
    att.scanned_at = datetime.now(timezone.utc)
    att.student_lat = float(student_lat) if student_lat else None
    att.student_lng = float(student_lng) if student_lng else None
    att.distance_meters = distance
    att.device_fingerprint = fingerprint
    att.ip_address = ip
    att.fraud_flags = fraud_flags

    AuditLog.log("SCAN_SUCCESS", user_id=student_id, resource_id=session_id,
                 ip_address=ip, extra_data={"distance": distance, "flags": fraud_flags})
    db.session.commit()

    # ── Notif SocketIO ─────────────────────────────────────────────────────
    from app import socketio
    socketio.emit("attendance_update", {
        "session_id": session_id,
        "student_id": student_id,
        "student_name": student.full_name,
        "group_id": att.group_id,
        "status": "present",
        "scanned_at": att.scanned_at.isoformat(),
        "distance": distance,
    }, room=f"session_{session_id}")

    return jsonify({
        "success": True,
        "message": "Présence enregistrée avec succès !",
        "distance": distance,
        "flags": fraud_flags,
    })


# ── Stats en temps réel ────────────────────────────────────────────────────
@bp.route("/session/<session_id>/stats")
@jwt_required(locations=["cookies", "headers"])
def session_stats(session_id):
    claims = get_jwt()
    if claims.get("role") != "professor":
        return jsonify({"error": "Accès refusé"}), 403

    session = Session.query.get_or_404(session_id)
    groups_data = []
    for group in session.groups:
        attendances = Attendance.query.filter_by(
            session_id=session_id, group_id=group.id).all()
        students_data = []
        for att in attendances:
            students_data.append({
                "id": att.student_id,
                "name": att.student.full_name,
                "status": att.status,
                "scanned_at": att.scanned_at.isoformat() if att.scanned_at else None,
            })
        present = sum(1 for a in attendances if a.status == "present")
        absent = sum(1 for a in attendances if a.status == "absent")
        pending = sum(1 for a in attendances if a.status == "pending")
        groups_data.append({
            "id": group.id,
            "name": group.name,
            "present": present,
            "absent": absent,
            "pending": pending,
            "total": len(attendances),
            "students": students_data,
        })

    return jsonify({
        "session_id": session_id,
        "status": session.status,
        "groups": groups_data,
    })


# ── Dashboard stats ────────────────────────────────────────────────────────
@bp.route("/professor/stats")
@jwt_required(locations=["cookies", "headers"])
def professor_stats():
    claims = get_jwt()
    if claims.get("role") != "professor":
        return jsonify({"error": "Accès refusé"}), 403
    prof_id = get_jwt_identity()

    from sqlalchemy import func, extract
    from datetime import timedelta

    # Évolution mensuelle des 6 derniers mois
    monthly = []
    now = datetime.now(timezone.utc)
    for i in range(5, -1, -1):
        month_dt = now.replace(day=1) - __import__('dateutil.relativedelta', fromlist=['relativedelta']).relativedelta(months=i) \
            if False else None
        # Simplifié : on groupe directement
    
    att_by_month = db.session.query(
        func.extract("year", Attendance.created_at).label("yr"),
        func.extract("month", Attendance.created_at).label("mo"),
        func.count(Attendance.id).label("total"),
        func.sum(db.case((Attendance.status == "present", 1), else_=0)).label("present"),
    ).join(Session).filter(
        Session.professor_id == prof_id
    ).group_by("yr", "mo").order_by("yr", "mo").limit(6).all()

    return jsonify({
        "monthly": [
            {"year": int(r.yr), "month": int(r.mo),
             "rate": round(int(r.present or 0) / max(int(r.total), 1) * 100, 1)}
            for r in att_by_month
        ]
    })
