from __future__ import annotations

import bcrypt
import secrets

from fastapi import HTTPException, Request
from sqlalchemy import text
from sqlalchemy.orm import Session


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def csrf_token(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    return token


def require_csrf(request: Request) -> None:
    expected = request.session.get("csrf_token")
    actual = request.headers.get("x-csrf-token", "")
    if not expected or not secrets.compare_digest(str(expected), actual):
        raise HTTPException(status_code=403, detail="Session token expired. Refresh the page and try again.")


def current_user(request: Request, db: Session) -> dict:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Please sign in first.")
    row = db.execute(
        text(
            "SELECT u.users_id, u.store_id, u.users_role, u.users_fname, u.users_mname, "
            "u.users_lname, u.users_sname, c.cre_username "
            "FROM users u JOIN credential c ON c.users_id = u.users_id "
            "WHERE u.users_id = :user_id LIMIT 1"
        ),
        {"user_id": int(user_id)},
    ).mappings().first()
    if not row:
        request.session.clear()
        raise HTTPException(status_code=401, detail="Account no longer exists. Sign in again.")
    return dict(row)


def require_owner(user: dict) -> None:
    if user.get("users_role") != "owner":
        raise HTTPException(status_code=403, detail="Owner access is required for this action.")
