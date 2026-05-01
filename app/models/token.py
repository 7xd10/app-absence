"""
Token models - JWT Blacklist & Password Reset
"""
import uuid
import secrets
from datetime import datetime, timezone, timedelta
from app import db


class RevokedToken(db.Model):
    """Blacklist des JWT révoqués (logout)."""
    __tablename__ = "revoked_tokens"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    jti = db.Column(db.String(255), unique=True, nullable=False, index=True)
    revoked_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at = db.Column(db.DateTime(timezone=True))

    @classmethod
    def is_revoked(cls, jti: str) -> bool:
        return cls.query.filter_by(jti=jti).first() is not None

    @classmethod
    def revoke(cls, jti: str, expires_at=None) -> "RevokedToken":
        token = cls(jti=jti, expires_at=expires_at)
        db.session.add(token)
        db.session.commit()
        return token

    def __repr__(self) -> str:
        return f"<RevokedToken {self.jti}>"


class PasswordResetToken(db.Model):
    """Tokens de réinitialisation de mot de passe (valides 15 minutes)."""
    __tablename__ = "password_reset_tokens"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    token = db.Column(db.String(100), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    used = db.Column(db.Boolean, default=False)

    user = db.relationship("User", backref=db.backref("reset_tokens", lazy="dynamic"))

    @classmethod
    def create_for_user(cls, user_id: str, expiry_minutes: int = 15) -> "PasswordResetToken":
        # Invalider les anciens tokens
        cls.query.filter_by(user_id=user_id, used=False).update({"used": True})
        db.session.flush()

        token = cls(
            user_id=user_id,
            token=secrets.token_urlsafe(48),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=expiry_minutes),
        )
        db.session.add(token)
        db.session.commit()
        return token

    @property
    def is_valid(self) -> bool:
        return not self.used and self.expires_at > datetime.now(timezone.utc)

    def __repr__(self) -> str:
        return f"<PasswordResetToken {self.user_id}>"
