"""
AuditLog model - Journal d'audit complet
"""
import uuid
from datetime import datetime, timezone
from app import db


class AuditLog(db.Model):
    """Journal de toutes les actions sensibles."""
    __tablename__ = "audit_logs"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)
    action = db.Column(db.String(100), nullable=False)   # ex: LOGIN, LOGOUT, QR_SCAN
    resource_type = db.Column(db.String(50))              # ex: session, group, user
    resource_id = db.Column(db.String(36))
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(500))
    extra_data = db.Column(db.JSON)
    success = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    @classmethod
    def log(cls, action: str, user_id: str = None, resource_type: str = None,
            resource_id: str = None, ip_address: str = None, user_agent: str = None,
            extra_data: dict = None, success: bool = True):
        entry = cls(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=ip_address,
            user_agent=user_agent,
            extra_data=extra_data or {},
            success=success,
        )
        db.session.add(entry)
        # Ne pas commit ici – laisser le caller gérer la transaction
        return entry

    def __repr__(self) -> str:
        return f"<AuditLog {self.action} by {self.user_id}>"
