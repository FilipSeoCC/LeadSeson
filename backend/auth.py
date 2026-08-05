"""Shared API-key check for write endpoints.

Split out of backend/api.py so other routers (backend/dashboard.py) can
depend on it without importing backend/api.py itself and creating a
circular import (api.py mounts those routers).
"""
from fastapi import Header, HTTPException
import os


def require_api_key(x_api_key: str | None = Header(default=None)):
    expected = os.getenv("LEADSEASON_API_KEY", "")
    if not expected:
        # No key configured: auth is a no-op locally, but every write endpoint stays
        # unprotected until LEADSEASON_API_KEY is set — required before any public deploy.
        return
    if x_api_key != expected:
        raise HTTPException(status_code=401, detail="Nieprawidłowy lub brakujący X-API-Key.")
