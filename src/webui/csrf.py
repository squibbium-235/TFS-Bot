"""Session CSRF token checked on unsafe HTTP methods.

The token lives in the session. Routes accept it as the form field
``_csrf_token`` or the ``X-CSRF-Token`` header, compared with
hmac.compare_digest. Safe methods are not checked.
"""

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
    """Return the session token, creating a URL-safe one on first use.

    A missing or non-string value is replaced. Calling this from a
    template therefore writes the session.
    """
    token = session.get(CSRF_SESSION_KEY)
    
    if not isinstance(token, str,) or not token:
        token = secrets.token_urlsafe(32)
        
        session[CSRF_SESSION_KEY] = token
        
    return token

def validate_csrf() -> None:
    """Abort with 400 unless the posted token matches the session.

    Registered as a before_request hook. Methods other than POST, PUT,
    PATCH, and DELETE return immediately. Either side failing the string
    check, or a digest mismatch, is a 400.
    """
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