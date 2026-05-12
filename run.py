"""
EuroPresence - Point d'entrée de l'application
"""
from app import create_app, socketio, db
from sqlalchemy import text

app = create_app()

with app.app_context():
    try:
        db.session.execute(text("ALTER TABLE users ADD COLUMN profile_picture TEXT;"))
        db.session.commit()
    except Exception:
        db.session.rollback()
    
    try:
        db.session.execute(text("ALTER TABLE users ADD COLUMN face_descriptor TEXT;"))
        db.session.commit()
    except Exception:
        db.session.rollback()

if __name__ == "__main__":
    socketio.run(
        app,
        host="0.0.0.0",
        port=5000,
        debug=True,
        use_reloader=True,
        log_output=True,
        allow_unsafe_werkzeug=True,
    )
