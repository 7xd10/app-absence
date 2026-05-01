"""
Service Email - Envoi des emails transactionnels
"""
from flask import current_app, render_template_string
from flask_mail import Message
from app import mail


# ── Templates d'emails (Design Institutionnel Premium) ───────────────────
EMAIL_BASE = """
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    body { font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; background-color: #f4f7f9; margin: 0; padding: 0; -webkit-font-smoothing: antialiased; }
    .wrapper { max-width: 600px; margin: 40px auto; background-color: #ffffff; border-radius: 12px; box-shadow: 0 10px 30px rgba(0,0,0,0.05); overflow: hidden; border: 1px solid #e1e8ed; }
    .header { background: linear-gradient(135deg, #003882 0%, #005BBB 100%); padding: 40px 20px; text-align: center; }
    .header h1 { color: #ffffff; font-size: 26px; font-weight: 300; margin: 0; letter-spacing: 1px; }
    .header p { color: rgba(255,255,255,0.8); font-size: 12px; text-transform: uppercase; letter-spacing: 2px; margin-top: 8px; }
    .body { padding: 45px 50px; color: #334155; line-height: 1.6; }
    .body h2 { color: #0f172a; font-size: 20px; font-weight: 600; margin-bottom: 25px; }
    .body p { font-size: 15px; margin-bottom: 20px; }
    .btn { display: inline-block; background-color: #003882; color: #ffffff !important; padding: 16px 35px; border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 15px; margin: 25px 0; transition: background 0.3s ease; }
    .footer { background-color: #f8fafc; padding: 30px 50px; text-align: center; color: #64748b; font-size: 12px; border-top: 1px solid #f1f5f9; }
    .info-card { background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 25px; margin: 25px 0; }
    .info-label { color: #64748b; font-size: 12px; text-transform: uppercase; margin-bottom: 5px; font-weight: 600; }
    .info-value { color: #1e293b; font-size: 16px; font-weight: 600; margin-bottom: 15px; }
    .temp-pwd { font-family: 'Courier New', Courier, monospace; font-size: 24px; color: #003882; letter-spacing: 4px; font-weight: 700; margin: 10px 0; }
    .warning-box { background-color: #fff5f5; border-left: 4px solid #ef4444; padding: 15px; border-radius: 0 6px 6px 0; margin-top: 25px; }
    .warning-text { color: #b91c1c; font-size: 13px; margin: 0; font-weight: 500; }
  </style>
</head>
<body>
  <div class="wrapper">
    <div class="header">
      <h1>🎓 EuroPresence</h1>
      <p>Université Euro-Méditerranéenne de Fès</p>
    </div>
    <div class="body">
      {{ content | safe }}
    </div>
    <div class="footer">
      <p>© 2025 EuroPresence – Service Numérique UEMF<br>Ce message est généré automatiquement par le système de gestion des présences.</p>
    </div>
  </div>
</body>
</html>
"""


def _send(to: str, subject: str, html_content: str) -> bool:
    """Envoie un email HTML (avec fallback local si SMTP non configuré)."""
    try:
        body = render_template_string(EMAIL_BASE, content=html_content)
        
        # Fallback local si pas d'identifiants SMTP
        if not current_app.config.get("MAIL_USERNAME") or "your-email" in current_app.config.get("MAIL_USERNAME"):
            import os
            from datetime import datetime
            folder = "emails_recus"
            if not os.path.exists(folder):
                os.makedirs(folder)
            
            filename = f"{folder}/{datetime.now().strftime('%Y%m%d_%H%M%S')}_{to.replace('@','_')}.html"
            with open(filename, "w", encoding="utf-8") as f:
                f.write(body)
            current_app.logger.info(f"[EMAIL SIMULATION] Message sauvegardé dans {filename}")
            return True

        msg = Message(subject=subject, recipients=[to], html=body)
        mail.send(msg)
        return True
    except Exception as e:
        current_app.logger.error(f"[EMAIL] Erreur envoi à {to}: {e}")
        return False


def send_confirmation_email(user, confirm_url: str) -> bool:
    """Email de confirmation d'inscription."""
    content = f"""
    <h2>Finalisation de votre inscription</h2>
    <p>Bonjour <strong>{user.first_name}</strong>,</p>
    <p>Votre compte a été créé avec succès sur la plateforme EuroPresence. Pour activer vos accès, veuillez confirmer votre adresse électronique en cliquant sur le bouton ci-dessous :</p>
    <div style="text-align:center;">
      <a href="{confirm_url}" class="btn">Confirmer mon adresse email</a>
    </div>
    <p style="font-size: 13px; color: #64748b;">Note : Ce lien de confirmation est valide pour une durée de 24 heures.</p>
    """
    return _send(user.email, "✅ Activation de votre compte – EuroPresence", content)


def send_password_reset_email(user, reset_url: str) -> bool:
    """Email de réinitialisation de mot de passe."""
    content = f"""
    <h2>Réinitialisation de votre mot de passe</h2>
    <p>Bonjour <strong>{user.first_name}</strong>,</p>
    <p>Nous avons reçu une demande de réinitialisation de mot de passe pour votre compte EuroPresence.</p>
    <div style="text-align:center;">
      <a href="{reset_url}" class="btn">Définir un nouveau mot de passe</a>
    </div>
    <div class="warning-box">
      <p class="warning-text">⚠️ Par mesure de sécurité, ce lien expirera dans 15 minutes. Si vous n'êtes pas à l'origine de cette demande, vous pouvez ignorer cet email.</p>
    </div>
    """
    return _send(user.email, "🔑 Réinitialisation de mot de passe – EuroPresence", content)


def send_temp_password_email(user, temp_password: str, login_url: str) -> bool:
    """Email avec mot de passe temporaire pour les étudiants importés."""
    content = f"""
    <h2>Vos accès à la plateforme EuroPresence</h2>
    <p>Bonjour <strong>{user.first_name} {user.last_name}</strong>,</p>
    <p>Nous vous informons que votre compte étudiant vient d'être configuré sur <strong>EuroPresence</strong>, la solution institutionnelle de suivi des présences de l'UEMF.</p>
    <p>Vous trouverez ci-dessous vos identifiants de connexion provisoires :</p>
    
    <div class="info-card">
      <div class="info-label">Identifiant (Email)</div>
      <div class="info-value">{user.email}</div>
      <div class="info-label">Mot de passe temporaire</div>
      <div class="temp-pwd">{temp_password}</div>
    </div>

    <div class="warning-box">
      <p class="warning-text">ℹ️ Ce mot de passe est temporaire. Vous serez invité(e) à le personnaliser lors de votre première connexion pour garantir la sécurité de votre compte.</p>
    </div>

    <div style="text-align:center;">
      <a href="{login_url}" class="btn">Accéder à mon espace étudiant</a>
    </div>
    
    <p style="font-size: 13px; color: #64748b; margin-top: 30px;">Si vous rencontrez des difficultés techniques, veuillez contacter le support ou votre professeur.</p>
    """
    return _send(user.email, "🎓 Vos accès EuroPresence – UEMF", content)


def send_warning_email(student, professor_name: str, subject: str, body_text: str) -> bool:
    """Email d'avertissement d'absence envoyé à un étudiant."""
    content = f"""
    <h2>Notification académique</h2>
    <p>Bonjour <strong>{student.first_name}</strong>,</p>
    <p>{body_text}</p>
    <p style="margin-top: 40px; border-top: 1px solid #f1f5f9; padding-top: 20px; font-style: italic; color: #64748b;">
      Message envoyé par le professeur <strong>{professor_name}</strong> via EuroPresence.
    </p>
    """
    return _send(student.email, f"⚠️ {subject} – EuroPresence", content)
