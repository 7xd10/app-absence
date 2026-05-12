"""
Session & Attendance models - Séances et présences
"""
import uuid
import hmac
import hashlib
import time
from datetime import datetime, timezone
from flask import current_app
from app import db

# ── Table d'association Session <-> Groupe ─────────────────────────────────
session_groups_table = db.Table(
    "session_groups",
    db.Column("session_id", db.String(36), db.ForeignKey("sessions.id"), primary_key=True),
    db.Column("group_id", db.String(36), db.ForeignKey("groups.id"), primary_key=True),
)


class Session(db.Model):
    """Séance de cours avec QR code dynamique."""
    __tablename__ = "sessions"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = db.Column(db.String(300), nullable=False)
    room = db.Column(db.String(100))
    session_type = db.Column(db.String(50), default="punctual")  # punctual | recurring
    status = db.Column(db.String(20), default="pending")  # pending | active | ended
    professor_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    # Horaires
    scheduled_at = db.Column(db.DateTime(timezone=True))
    started_at = db.Column(db.DateTime(timezone=True))
    ended_at = db.Column(db.DateTime(timezone=True))
    duration_minutes = db.Column(db.Integer, default=90)
    # Anti-fraude : localisation du professeur
    professor_lat = db.Column(db.Float)
    professor_lng = db.Column(db.Float)
    professor_ip = db.Column(db.String(45))
    # QR Code actuel
    current_qr_token = db.Column(db.String(500))
    qr_generated_at = db.Column(db.DateTime(timezone=True))

    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relations
    attendances = db.relationship("Attendance", backref="session", lazy="dynamic",
                                   cascade="all, delete-orphan")

    # ── QR Generation ──────────────────────────────────────────────────────
    def generate_qr_payload(self) -> dict:
        """
        Génère le contenu sécurisé du QR code (HMAC-SHA256).
        Le QR change toutes les QR_ROTATION_SECONDS secondes.
        """
        ts = int(time.time())
        # Arrondi au slot de rotation
        rotation = current_app.config.get("QR_ROTATION_SECONDS", 10)
        slot = ts - (ts % rotation)

        raw = f"{self.id}:{slot}"
        secret = current_app.config["HMAC_SECRET"].encode()
        sig = hmac.new(secret, raw.encode(), hashlib.sha256).hexdigest()

        return {
            "session_id": self.id,
            "timestamp": slot,
            "token": sig,
            "rotation": rotation,
        }

    @staticmethod
    def verify_qr_payload(session_id: str, timestamp: int, token: str) -> bool:
        """Vérifie qu'un QR code est valide et non expiré."""
        rotation = current_app.config.get("QR_ROTATION_SECONDS", 10)
        now_slot = int(time.time())
        now_slot = now_slot - (now_slot % rotation)

        # On accepte le slot actuel et le slot précédent (tolérance réseau)
        valid_slots = [now_slot, now_slot - rotation]
        if timestamp not in valid_slots:
            return False

        raw = f"{session_id}:{timestamp}"
        secret = current_app.config["HMAC_SECRET"].encode()
        expected = hmac.new(secret, raw.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, token)

    # ── Stats ──────────────────────────────────────────────────────────────
    @property
    def present_count(self) -> int:
        return self.attendances.filter_by(status="present").count()

    @property
    def absent_count(self) -> int:
        return self.attendances.filter_by(status="absent").count()

    @property
    def total_count(self) -> int:
        return self.attendances.count()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "room": self.room,
            "status": self.status,
            "professor_id": self.professor_id,
            "scheduled_at": self.scheduled_at.isoformat() if self.scheduled_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "duration_minutes": self.duration_minutes,
            "present_count": self.present_count,
            "absent_count": self.absent_count,
            "total_count": self.total_count,
        }

    def __repr__(self) -> str:
        return f"<Session {self.title} [{self.status}]>"


class Attendance(db.Model):
    """Enregistrement de présence pour un étudiant dans une séance."""
    __tablename__ = "attendances"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = db.Column(db.String(36), db.ForeignKey("sessions.id"), nullable=False)
    student_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    group_id = db.Column(db.String(36), db.ForeignKey("groups.id"), nullable=False)
    status = db.Column(db.String(20), default="absent")  # present | absent | pending | late
    scanned_at = db.Column(db.DateTime(timezone=True))
    # Anti-fraude
    student_lat = db.Column(db.Float)
    student_lng = db.Column(db.Float)
    distance_meters = db.Column(db.Float)
    device_fingerprint = db.Column(db.String(255))
    ip_address = db.Column(db.String(45))
    wifi_bssid = db.Column(db.String(100))
    fraud_flags = db.Column(db.JSON, default=list)  # liste des alertes fraud
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.UniqueConstraint("session_id", "student_id", name="uq_session_student"),
    )

    # Relation pour pouvoir faire att.group
    group = db.relationship("Group")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "student_id": self.student_id,
            "group_id": self.group_id,
            "status": self.status,
            "scanned_at": self.scanned_at.isoformat() if self.scanned_at else None,
            "distance_meters": self.distance_meters,
            "fraud_flags": self.fraud_flags,
        }

    def __repr__(self) -> str:
        return f"<Attendance {self.student_id} @ {self.session_id} [{self.status}]>"
