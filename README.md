# EuroPresence 🎓
**Solution de Gestion des Présences Universitaires par QR Code Dynamique**
*Université Euro-Méditerranéenne de Fès (UEMF)*

---

## 🚀 Installation Locale

### Prérequis
- Python 3.11+
- PostgreSQL 14+
- Redis 7+

### Étapes

```bash
# 1. Cloner / Accéder au dossier
cd "app absence"

# 2. Environnement virtuel
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate    # Linux/Mac

# 3. Installer les dépendances
pip install -r requirements.txt

# 4. Configurer l'environnement
copy .env.example .env
# Éditer .env avec vos valeurs (BDD, email, secrets)

# 5. Créer la base de données PostgreSQL
createdb europresence_db

# 6. Lancer l'application
python run.py
```

L'application sera accessible sur **http://localhost:5000**

---

## 🐳 Déploiement Docker

```bash
# 1. Copier et configurer les variables
copy .env.example .env
# Éditer .env avec des secrets forts pour la production

# 2. Lancer tous les services
docker-compose up -d

# 3. Vérifier les logs
docker-compose logs -f app
```

Services démarrés :
- **App** : http://localhost:5000
- **PostgreSQL** : localhost:5432
- **Redis** : localhost:6379

---

## 🏗️ Architecture du Projet

```
app absence/
├── run.py                          # Point d'entrée
├── requirements.txt                # Dépendances Python
├── Dockerfile                      # Image Docker
├── docker-compose.yml              # Services Docker
├── .env.example                    # Template variables d'env
│
└── app/
    ├── __init__.py                 # Factory Flask + extensions
    ├── socketio_events.py          # Événements SocketIO temps réel
    │
    ├── models/                     # Modèles SQLAlchemy
    │   ├── user.py                 # Professeur + Étudiant
    │   ├── group.py                # Groupes + membres
    │   ├── session.py              # Séances + présences + QR HMAC
    │   ├── token.py                # JWT blacklist + reset tokens
    │   ├── message.py              # Communications internes
    │   ├── audit.py                # Journal d'audit
    │   └── device.py              # Empreintes appareils
    │
    ├── services/
    │   ├── email_service.py        # Emails HTML transactionnels
    │   ├── qr_service.py           # Génération QR code HMAC
    │   └── export_service.py       # Export Excel / CSV / PDF
    │
    ├── main/routes.py              # Landing page
    ├── auth/routes.py              # Login, Register, Reset
    ├── professor/routes.py         # Dashboard prof + CRUD
    ├── student/routes.py           # Dashboard étudiant + scan
    ├── api/routes.py               # REST API + anti-fraude
    │
    ├── templates/
    │   ├── base.html               # Template de base (Tailwind)
    │   ├── main/index.html         # Landing page premium
    │   ├── auth/                   # Login, Register, Reset
    │   ├── professor/              # Dashboard, Groupes, Sessions, QR
    │   └── student/                # Dashboard, Scanner, Historique
    │
    └── static/
        └── templates/
            └── template_etudiants.csv   # Template import CSV
```

---

## 🔐 Système Anti-Fraude (5 niveaux)

### 1. QR Code Dynamique (HMAC-SHA256)
- Le QR code change automatiquement toutes les **10 secondes**
- Contenu signé : `HMAC_SHA256(session_id + timestamp_slot, HMAC_SECRET)`
- Un QR capturé est inutilisable après 10 secondes → **partage impossible**
- La vérification accepte le slot actuel et le précédent (tolérance réseau)

### 2. Géofencing GPS
- Le professeur partage sa position GPS lors du démarrage de la session
- Chaque étudiant doit être dans un **rayon de 80 mètres** autour de la salle
- Calcul de distance via la formule **Haversine** (sphère terrestre)
- Refus de la localisation → marqué **Absent automatiquement**
- Distance enregistrée pour chaque présence dans la base de données

### 3. Empreinte d'Appareil (Device Fingerprint)
- L'empreinte est générée côté client à partir de :
  `user-agent + langue + résolution écran + CPU cores`
- Un compte étudiant ne peut être actif que sur **un seul appareil**
- Un nouvel appareil déclenche un flag `NEW_DEVICE` dans les fraud_flags

### 4. JWT Sécurisé
- Access token (courte durée) + Refresh token
- Blacklist des tokens révoqués en base de données
- Chargement depuis cookies HTTP-Only **et** headers Authorization
- Headers de sécurité : `X-Frame-Options`, `X-Content-Type-Options`, CSP

### 5. Rate Limiting
- **Login** : max 5 tentatives/minute par IP (Flask-Limiter + Redis)
- **Scan QR** : max 10 requêtes/minute par compte
- **Mot de passe oublié** : max 3 requêtes/minute
- Compte bloqué 15 minutes après 5 échecs consécutifs

---

## 📧 Système de Mot de Passe Temporaire

### Flux d'inscription d'un étudiant

```
Professeur importe CSV / ajoute manuellement
         ↓
Création compte étudiant (is_active=False, is_temp_password=True)
         ↓
Génération mot de passe temporaire sécurisé (12 caractères aléatoires)
         ↓
Envoi email automatique avec :
  - Identifiants (email + mot de passe temporaire)
  - Lien direct vers la page de connexion
         ↓
Étudiant se connecte avec les identifiants temporaires
         ↓
Redirection obligatoire vers "Changer mon mot de passe"
(Accès au scanner QR bloqué tant que is_temp_password=True)
         ↓
Étudiant définit son nouveau mot de passe
→ is_temp_password=False, is_active=True
         ↓
Accès complet activé (Scanner QR, Historique, etc.)
```

### Renvoi d'un mot de passe temporaire
Le professeur peut depuis la vue groupe, retirer et ré-ajouter un étudiant,
ce qui génère automatiquement un nouveau mot de passe temporaire.

---

## 📊 Fonctionnalités Principales

| Fonctionnalité | Détail |
|---|---|
| QR Dynamique | Rotation toutes les 10s, HMAC-SHA256 |
| Géofencing | Rayon configurable (défaut 80m) |
| Temps réel | WebSocket SocketIO, live attendance |
| Import CSV/Excel | Template téléchargeable, envoi auto des accès |
| Export | Excel (openpyxl), PDF (reportlab), CSV – avec logo UEMF |
| Messages | Internes + email, modèles prédéfinis |
| Multi-groupes | Une session peut couvrir plusieurs groupes |
| Audit log | Toutes les actions sensibles tracées |
| PWA Ready | manifest.json, responsive mobile-first |
| Multilingue | Structure prête pour i18n (FR/EN/AR) |

---

## 🔧 Variables d'Environnement Importantes

| Variable | Description | Défaut |
|---|---|---|
| `SECRET_KEY` | Clé secrète Flask | ⚠️ À changer |
| `JWT_SECRET_KEY` | Clé JWT | ⚠️ À changer |
| `HMAC_SECRET` | Clé HMAC pour QR codes | ⚠️ À changer |
| `DATABASE_URL` | URL PostgreSQL | localhost |
| `REDIS_URL` | URL Redis | localhost |
| `QR_ROTATION_SECONDS` | Fréquence rotation QR | 10 |
| `GEOFENCE_RADIUS_METERS` | Rayon géofencing | 80 |
| `MAX_LOGIN_ATTEMPTS` | Tentatives avant blocage | 5 |
| `PASSWORD_RESET_EXPIRY_MINUTES` | Durée validité reset | 15 |

---

## 📄 Licence
© 2025 EuroPresence – Université Euro-Méditerranéenne de Fès (UEMF)
Tous droits réservés.
