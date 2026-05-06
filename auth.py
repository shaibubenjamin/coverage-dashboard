"""
auth.py — Password hashing, JWT helpers, FastAPI permission dependencies.
"""
import os
import datetime
import secrets
from typing import List

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext
import jwt

SECRET_KEY      = os.environ.get("SECRET_KEY", "sarmaan_amr_sokoto_2024_secret")
ALGORITHM       = "HS256"
TOKEN_TTL_HOURS = 8

# HS256 requires ≥32-byte keys (PyJWT emits InsecureKeyLengthWarning per call
# otherwise). Fail loudly at boot rather than spamming the logs on every JWT
# encode/decode. The .env.example suggests how to generate a fresh key.
if len(SECRET_KEY.encode("utf-8")) < 32:
    raise RuntimeError(
        f"SECRET_KEY is {len(SECRET_KEY.encode('utf-8'))} bytes — must be ≥32 bytes for HS256.\n"
        "Generate one with:  python3 -c 'import secrets; print(secrets.token_urlsafe(48))'\n"
        "and set it in your .env."
    )

pwd_ctx  = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()


# ── Password ───────────────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return pwd_ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_ctx.verify(plain, hashed)


# ── Token ──────────────────────────────────────────────────────────────────────

def create_access_token(
    user_id:     int,
    email:       str,
    name:        str,
    role:        str,
    permissions: List[str],
    lgas:        List[str],
    project_ids: List[int],
) -> str:
    payload = {
        "sub":         str(user_id),
        "email":       email,
        "name":        name,
        "role":        role,
        "permissions": permissions,
        "lgas":        lgas,
        "project_ids": project_ids,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=TOKEN_TTL_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired — please log in again")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")


# ── FastAPI dependencies ───────────────────────────────────────────────────────

def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """Decode the Bearer token and return its payload as a dict."""
    return decode_token(creds.credentials)


def require_permission(perm: str):
    """Dependency factory — 403 if the token lacks *perm*."""
    def checker(user: dict = Depends(get_current_user)) -> dict:
        if perm not in user.get("permissions", []):
            raise HTTPException(403, f"Permission denied: requires '{perm}'")
        return user
    return checker


def require_role(*roles: str):
    """Dependency factory — 403 if user role not in *roles*."""
    def checker(user: dict = Depends(get_current_user)) -> dict:
        if user.get("role") not in roles:
            raise HTTPException(403, "Access denied for your role")
        return user
    return checker


def lga_filter(user: dict) -> List[str]:
    """
    Return the list of LGAs the user is restricted to.
    Empty list means no restriction (super_admin / admin).
    """
    if user.get("role") == "validator":
        return user.get("lgas", [])
    return []


# ── Invite token ───────────────────────────────────────────────────────────────

def generate_invite_token() -> str:
    return secrets.token_urlsafe(32)
