"""
Network helpers.
"""
from flask import request


def get_client_ip() -> str | None:
    """Return the real client IP, honoring proxy headers when present."""
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        # Use the left-most IP in the chain.
        ip = forwarded_for.split(",", 1)[0].strip()
        return ip or None

    real_ip = request.headers.get("X-Real-IP", "").strip()
    if real_ip:
        return real_ip

    return request.remote_addr or None
