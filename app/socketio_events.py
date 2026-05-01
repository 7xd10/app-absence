"""
SocketIO Events - Temps réel pour les sessions de présence
"""
from flask_socketio import join_room, leave_room, emit
from flask_jwt_extended import decode_token
from app import socketio
from app.models.session import Session


@socketio.on("join_session")
def on_join_session(data):
    """Un professeur rejoint la room de sa session."""
    token = data.get("token")
    session_id = data.get("session_id")
    try:
        decoded = decode_token(token)
        if decoded.get("role") != "professor":
            emit("error", {"message": "Accès refusé"})
            return
        join_room(f"session_{session_id}")
        emit("joined", {"session_id": session_id, "status": "ok"})
    except Exception as e:
        emit("error", {"message": str(e)})


@socketio.on("leave_session")
def on_leave_session(data):
    session_id = data.get("session_id")
    leave_room(f"session_{session_id}")


@socketio.on("connect")
def on_connect():
    emit("connected", {"status": "ok"})


@socketio.on("disconnect")
def on_disconnect():
    pass
