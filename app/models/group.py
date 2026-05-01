"""
Group model - Groupes d'étudiants gérés par les professeurs
"""
import uuid
from datetime import datetime, timezone
from app import db


class Group(db.Model):
    """Groupe d'étudiants."""
    __tablename__ = "groups"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(200), nullable=False)
    filiere = db.Column(db.String(200))       # Filière (ex: Génie Informatique)
    level = db.Column(db.String(50))           # Niveau (ex: S3, M1, L2)
    academic_year = db.Column(db.String(20))   # ex: 2024-2025
    description = db.Column(db.Text)
    professor_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc))
    is_active = db.Column(db.Boolean, default=True)

    # Relations
    members = db.relationship("GroupStudent", backref="group", lazy="dynamic",
                               cascade="all, delete-orphan")
    sessions = db.relationship("Session", secondary="session_groups",
                                backref="groups", lazy="dynamic")

    @property
    def student_count(self) -> int:
        return self.members.filter_by(is_active=True).count()

    @property
    def attendance_rate(self) -> float:
        """Taux de présence global du groupe (%)."""
        from app.models.session import Attendance, Session
        from sqlalchemy import func
        total = db.session.query(func.count(Attendance.id)).join(
            Session, Attendance.session_id == Session.id
        ).join(
            "session_groups_table"
        ).filter(
            Attendance.group_id == self.id
        ).scalar() or 0
        if total == 0:
            return 0.0
        present = db.session.query(func.count(Attendance.id)).filter(
            Attendance.group_id == self.id,
            Attendance.status == "present"
        ).scalar() or 0
        return round((present / total) * 100, 1)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "filiere": self.filiere,
            "level": self.level,
            "academic_year": self.academic_year,
            "description": self.description,
            "professor_id": self.professor_id,
            "student_count": self.student_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return f"<Group {self.name}>"


class GroupStudent(db.Model):
    """Association Groupe <-> Étudiant."""
    __tablename__ = "group_students"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    group_id = db.Column(db.String(36), db.ForeignKey("groups.id"), nullable=False)
    student_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    enrolled_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    is_active = db.Column(db.Boolean, default=True)

    __table_args__ = (
        db.UniqueConstraint("group_id", "student_id", name="uq_group_student"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "group_id": self.group_id,
            "student_id": self.student_id,
            "enrolled_at": self.enrolled_at.isoformat() if self.enrolled_at else None,
        }
