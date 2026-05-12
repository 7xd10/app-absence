"""
User model - Professeurs & Étudiants
"""
import uuid
import secrets
import string
from datetime import datetime, timezone
from app import db, bcrypt


class User(db.Model):
    """Modèle utilisateur unifié (professeur + étudiant)."""
    __tablename__ = "users"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    # Identité
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(30))
    # Rôle : 'professor' | 'student'
    role = db.Column(db.String(20), nullable=False, default="student")
    # Infos institutionnelles
    university = db.Column(db.String(200), default="Université Euro-Méditerranéenne de Fès")
    department = db.Column(db.String(200))          # pour les profs
    matricule = db.Column(db.String(50), unique=True, nullable=True)  # pour les étudiants
    # Sécurité
    password_hash = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=False)   # False tant que l'email n'est pas confirmé
    is_temp_password = db.Column(db.Boolean, default=False)  # True pour les étudiants importés
    temp_password_plain = db.Column(db.String(100), nullable=True) # Pour affichage prof (dure 1h)
    temp_password_expires_at = db.Column(db.DateTime(timezone=True), nullable=True)
    email_confirmed = db.Column(db.Boolean, default=False)
    email_confirm_token = db.Column(db.String(100), unique=True, nullable=True)
    # Timestamps
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc))
    last_login = db.Column(db.DateTime(timezone=True))
    # Brute-force
    failed_login_attempts = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime(timezone=True))
    profile_picture = db.Column(db.Text, nullable=True) # Base64 encoded image
    face_descriptor = db.Column(db.Text, nullable=True) # JSON string of 128 float array

    # ── Relations ──────────────────────────────────────────────────────────
    groups_taught = db.relationship("Group", backref="professor", lazy="dynamic",
                                    foreign_keys="Group.professor_id")
    group_memberships = db.relationship("GroupStudent", backref="student", lazy="dynamic")
    attendances = db.relationship("Attendance", backref="student", lazy="dynamic",
                                  foreign_keys="Attendance.student_id")
    sessions_created = db.relationship("Session", backref="professor", lazy="dynamic",
                                       foreign_keys="Session.professor_id")
    messages_sent = db.relationship("Message", backref="sender", lazy="dynamic",
                                    foreign_keys="Message.sender_id")
    messages_received = db.relationship("Message", backref="recipient", lazy="dynamic",
                                        foreign_keys="Message.recipient_id")
    devices = db.relationship("DeviceFingerprint", backref="user", lazy="dynamic")
    audit_logs = db.relationship("AuditLog", backref="user", lazy="dynamic")

    # ── Password ───────────────────────────────────────────────────────────
    def set_password(self, password: str) -> None:
        self.password_hash = bcrypt.generate_password_hash(password).decode("utf-8")

    def check_password(self, password: str) -> bool:
        return bcrypt.check_password_hash(self.password_hash, password)

    @staticmethod
    def generate_temp_password(length: int = 12) -> str:
        """Génère un mot de passe temporaire sécurisé."""
        alphabet = string.ascii_letters + string.digits + "!@#$%"
        return "".join(secrets.choice(alphabet) for _ in range(length))

    @staticmethod
    def generate_confirm_token() -> str:
        return secrets.token_urlsafe(32)

    # ── Helpers ────────────────────────────────────────────────────────────
    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def is_locked(self) -> bool:
        if self.locked_until and self.locked_until > datetime.now(timezone.utc):
            return True
        return False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "full_name": self.full_name,
            "email": self.email,
            "role": self.role,
            "university": self.university,
            "department": self.department,
            "matricule": self.matricule,
            "is_active": self.is_active,
            "is_temp_password": self.is_temp_password,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None,
        }

    def __repr__(self) -> str:
        return f"<User {self.email} [{self.role}]>"
