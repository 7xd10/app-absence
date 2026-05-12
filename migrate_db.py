from app import create_app, db
from sqlalchemy import text

app = create_app()

with app.app_context():
    try:
        db.session.execute(text("ALTER TABLE users ADD COLUMN profile_picture TEXT;"))
        print("Ajout profile_picture OK")
    except Exception as e:
        print("Ignoré (peut-être déjà présent):", e)
        db.session.rollback()
        
    try:
        db.session.execute(text("ALTER TABLE users ADD COLUMN face_descriptor TEXT;"))
        print("Ajout face_descriptor OK")
    except Exception as e:
        print("Ignoré (peut-être déjà présent):", e)
        db.session.rollback()
        
    db.session.commit()
    print("Migration terminée avec succès !")