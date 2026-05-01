"""
Message model - Communications internes
"""
import uuid
from datetime import datetime, timezone
from app import db


class Message(db.Model):
    """Messages entre professeur et étudiant(s)."""
    __tablename__ = "messages"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    sender_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    recipient_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)
    group_id = db.Column(db.String(36), db.ForeignKey("groups.id"), nullable=True)  # broadcast
    subject = db.Column(db.String(300))
    body = db.Column(db.Text, nullable=False)
    message_type = db.Column(db.String(50), default="info")  # info | warning | alert
    is_email_sent = db.Column(db.Boolean, default=False)
    is_read = db.Column(db.Boolean, default=False)
    template_used = db.Column(db.String(100))
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "sender_id": self.sender_id,
            "recipient_id": self.recipient_id,
            "group_id": self.group_id,
            "subject": self.subject,
            "body": self.body,
            "message_type": self.message_type,
            "is_read": self.is_read,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return f"<Message {self.id} [{self.message_type}]>"
