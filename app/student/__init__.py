"""
Student Blueprint - Espace Étudiant
"""
from flask import Blueprint

bp = Blueprint("student", __name__)

from app.student import routes  # noqa: E402, F401
