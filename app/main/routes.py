"""
Main routes - Landing page publique
"""
from flask import render_template
from app.main import bp


@bp.route("/")
def index():
    """Landing page EuroPresence."""
    return render_template("main/index.html")


@bp.route("/manifest.json")
def manifest():
    """PWA Manifest."""
    from flask import jsonify
    return jsonify({
        "name": "EuroPresence",
        "short_name": "EuroPresence",
        "description": "Gestion des présences universitaires par QR code – UEMF",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#003882",
        "theme_color": "#003882",
        "icons": [
            {"src": "/static/images/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/static/images/icon-512.png", "sizes": "512x512", "type": "image/png"},
        ]
    })
