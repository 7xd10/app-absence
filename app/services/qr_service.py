"""
Service QR Code - Génération et validation des QR codes dynamiques
"""
import io
import base64
import qrcode
import json
from qrcode.image.svg import SvgImage
from flask import current_app


def generate_qr_base64(session) -> str:
    """
    Génère un QR code PNG en base64 contenant le payload HMAC sécurisé.
    Le contenu change toutes les QR_ROTATION_SECONDS secondes.
    """
    payload = session.generate_qr_payload()
    # Encodage JSON du payload dans le QR
    data = json.dumps(payload)

    qr = qrcode.QRCode(
        version=2,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=3,
    )
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="#003882", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def generate_qr_payload_only(session) -> dict:
    """Retourne uniquement le payload JSON (pour l'API)."""
    return session.generate_qr_payload()


def validate_scan(data: dict, session) -> tuple[bool, str]:
    """
    Valide le scan QR d'un étudiant.
    Retourne (is_valid, reason).
    """
    required = {"session_id", "timestamp", "token"}
    if not required.issubset(data.keys()):
        return False, "Données QR incomplètes"

    if data["session_id"] != session.id:
        return False, "Session incorrecte"

    from app.models.session import Session as SessionModel
    ok = SessionModel.verify_qr_payload(
        session_id=data["session_id"],
        timestamp=int(data["timestamp"]),
        token=data["token"],
    )
    if not ok:
        return False, "QR code expiré ou invalide"

    return True, "OK"
