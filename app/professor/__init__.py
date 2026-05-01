"""
Professor Blueprint - Espace Professeur
"""
from flask import Blueprint

bp = Blueprint("professor", __name__)

from app.professor import routes  # noqa: E402, F401
