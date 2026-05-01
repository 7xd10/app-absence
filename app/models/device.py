"""
DeviceFingerprint model - Anti-fraude appareil unique par étudiant
"""
import uuid
from datetime import datetime, timezone
from app import db


class DeviceFingerprint(db.Model):
    """Empreinte d'appareil pour limiter un seul appareil actif par étudiant."""
    __tablename__ = "device_fingerprints"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    fingerprint = db.Column(db.String(255), nullable=False)
    user_agent = db.Column(db.String(500))
    ip_address = db.Column(db.String(45))
    is_trusted = db.Column(db.Boolean, default=True)
    first_seen = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_seen = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.UniqueConstraint("user_id", "fingerprint", name="uq_user_fingerprint"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "fingerprint": self.fingerprint[:8] + "...",  # tronqué pour sécurité
            "user_agent": self.user_agent,
            "is_trusted": self.is_trusted,
            "first_seen": self.first_seen.isoformat() if self.first_seen else None,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
        }

    def __repr__(self) -> str:
        return f"<DeviceFingerprint {self.user_id} [{self.fingerprint[:8]}...]>"
