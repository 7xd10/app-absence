"""
EuroPresence - Application Factory
Université Euro-Méditerranéenne de Fès (UEMF)
"""
import os
from urllib.parse import urlparse
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from flask_bcrypt import Bcrypt
from flask_mail import Mail
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_socketio import SocketIO
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()


def _is_local_redis(url: str | None) -> bool:
    if not url:
        return False
    try:
        host = urlparse(url).hostname
    except Exception:
        return False
    return host in {"localhost", "127.0.0.1", "::1"}

# ── Extensions (instanciées sans app) ──────────────────────────────────────
db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()
bcrypt = Bcrypt()
mail = Mail()
socketio = SocketIO()
limiter = Limiter(key_func=get_remote_address)

def create_app(config_name: str = "development") -> Flask:
    """Application factory."""
    app = Flask(__name__)

    redis_url = os.environ.get("REDIS_URL")
    ratelimit_storage_uri = os.environ.get("RATELIMIT_STORAGE_URI")
    if not ratelimit_storage_uri:
        if not redis_url or _is_local_redis(redis_url):
            ratelimit_storage_uri = "memory://"
        else:
            ratelimit_storage_uri = redis_url

    # ── Configuration ──────────────────────────────────────────────────────
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-secret-change-me"),
        SQLALCHEMY_DATABASE_URI=os.environ.get(
            "DATABASE_URL",
            "sqlite:///europresence.db"
        ),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={
            "pool_pre_ping": True,
            "pool_recycle": 300,
        },
        # JWT
        JWT_SECRET_KEY=os.environ.get("JWT_SECRET_KEY", "jwt-secret-change-me"),
        JWT_ACCESS_TOKEN_EXPIRES=False,   # géré par cookie / localStorage
        JWT_TOKEN_LOCATION=["headers", "cookies"],
        JWT_COOKIE_SECURE=False,          # True en production (HTTPS)
        JWT_COOKIE_CSRF_PROTECT=False,
        # Mail
        MAIL_SERVER=os.environ.get("MAIL_SERVER", "smtp.gmail.com"),
        MAIL_PORT=int(os.environ.get("MAIL_PORT", 587)),
        MAIL_USE_TLS=os.environ.get("MAIL_USE_TLS", "True") == "True",
        MAIL_USERNAME=os.environ.get("MAIL_USERNAME"),
        MAIL_PASSWORD=os.environ.get("MAIL_PASSWORD"),
        MAIL_DEFAULT_SENDER=os.environ.get("MAIL_DEFAULT_SENDER", "EuroPresence <noreply@europresence.ma>"),
        # Redis / Limiter
        RATELIMIT_STORAGE_URI=ratelimit_storage_uri,
        # App
        APP_NAME="EuroPresence",
        UNIVERSITY_NAME="Université Euro-Méditerranéenne de Fès",
        HMAC_SECRET=os.environ.get("HMAC_SECRET", "hmac-secret-change-me"),
        QR_ROTATION_SECONDS=int(os.environ.get("QR_ROTATION_SECONDS", 10)),
        GEOFENCE_RADIUS_METERS=int(os.environ.get("GEOFENCE_RADIUS_METERS", 80)),
        MAX_LOGIN_ATTEMPTS=int(os.environ.get("MAX_LOGIN_ATTEMPTS", 5)),
        PASSWORD_RESET_EXPIRY_MINUTES=int(os.environ.get("PASSWORD_RESET_EXPIRY_MINUTES", 15)),
        FRONTEND_URL=os.environ.get("FRONTEND_URL", "http://localhost:5000"),
        # Upload
        MAX_CONTENT_LENGTH=16 * 1024 * 1024,  # 16 MB
    )

    # ── Extensions init ────────────────────────────────────────────────────
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    bcrypt.init_app(app)
    mail.init_app(app)
    limiter.init_app(app)
    socketio.init_app(
        app,
        cors_allowed_origins="*",
        message_queue=redis_url if redis_url and not _is_local_redis(redis_url) else None,
        async_mode="threading"
    )
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # ── Security Headers ───────────────────────────────────────────────────
    @app.after_request
    def add_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(self), camera=(self)"
        if not app.debug:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    # ── JWT Blacklist ──────────────────────────────────────────────────────
    from app.models.token import RevokedToken

    @jwt.token_in_blocklist_loader
    def check_if_token_revoked(jwt_header, jwt_payload):
        jti = jwt_payload["jti"]
        return RevokedToken.is_revoked(jti)

    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        from flask import jsonify, redirect, url_for, flash, request
        if request.path.startswith("/api/") or request.is_json:
            return jsonify({"error": "Token expiré", "code": "TOKEN_EXPIRED"}), 401
        flash("Votre session a expiré. Veuillez vous reconnecter.", "warning")
        return redirect(url_for("auth.login"))

    @jwt.invalid_token_loader
    def invalid_token_callback(error):
        from flask import jsonify, redirect, url_for, flash, request
        if request.path.startswith("/api/") or request.is_json:
            return jsonify({"error": "Token invalide", "code": "TOKEN_INVALID"}), 401
        flash("Session invalide. Veuillez vous reconnecter.", "error")
        return redirect(url_for("auth.login"))

    @jwt.unauthorized_loader
    def missing_token_callback(error):
        from flask import jsonify, redirect, url_for, flash, request
        if request.path.startswith("/api/") or request.is_json:
            return jsonify({"error": "Token manquant", "code": "TOKEN_MISSING"}), 401
        flash("Veuillez vous connecter pour accéder à cette page.", "warning")
        return redirect(url_for("auth.login"))

    # ── Blueprints ─────────────────────────────────────────────────────────
    from app.main import bp as main_bp
    from app.auth import bp as auth_bp
    from app.professor import bp as professor_bp
    from app.student import bp as student_bp
    from app.api import bp as api_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(professor_bp, url_prefix="/professeur")
    app.register_blueprint(student_bp, url_prefix="/etudiant")
    app.register_blueprint(api_bp, url_prefix="/api")

    # ── SocketIO Events ────────────────────────────────────────────────────
    from app import socketio_events  # noqa: F401

    # ── Context Processor ──────────────────────────────────────────────────
    @app.context_processor
    def inject_current_user():
        from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
        from app.models.user import User
        try:
            verify_jwt_in_request(optional=True, locations=["cookies", "headers"])
            identity = get_jwt_identity()
            if identity:
                user = User.query.get(identity)
                return dict(current_user=user)
        except Exception:
            pass
        return dict(current_user=None)

    # ── Create tables (dev only) ───────────────────────────────────────────
    with app.app_context():
        db.create_all()

    return app
