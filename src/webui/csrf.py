from __future__ import annotations

import hmac
import secrets

from flask import (
    abort,
    request,
    session,
)

CSRF_SESSION_KEY = ("_csrf_token")

def csrf_token() -> str:
    token = session.get(CSRF_SESSION_KEY)
    
    if not isinstance(token, str,) or not token:
        token = secrets.token_urlsafe(32)
        
        session[CSRF_SESSION_KEY] = token
        
    return token

def validate_csrf() -> None:
    if request.method not in {
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
    }:
        return
    
    expected = session.get(CSRF_SESSION_KEY)
    supplied = (request.form.get("_csrf_token") or request.headers.get("X-CSRF-Token"))
    
    if(not isinstance(expected, str) or not isinstance(supplied, str,) or not hmac.compare_digest(expected, supplied,)):
        abort(400, description=("Invalid or missing CSRF token."),)