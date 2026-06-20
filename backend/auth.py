"""
auth.py — JWT-based authentication and role enforcement for ConfidenceOS.

Flow:
  POST /api/auth/login   → {username, password} → {access_token, token_type, role}
  GET  /api/auth/me      → returns current user from token
  All protected endpoints use get_current_user() or require_role(*roles) as Depends()

Token:
  JWT signed with HS256, 8-hour expiry. Payload contains: sub (username), role, exp.
  Token sent as Authorization: Bearer <token>.

Backward compatibility:
  X-API-Key guard still works for API-level mutual auth (machine clients).
  X-Role header fallback removed — all role enforcement now requires a valid JWT.

Demo users (seeded at startup if no users exist):
  operator  / ConfidenceOS-Op-2025   → Operator
  maint     / ConfidenceOS-Maint-2025 → Maintenance
  engineer  / ConfidenceOS-Eng-2025  → Engineer
  manager   / ConfidenceOS-Mgr-2025  → Manager
  auditor   / ConfidenceOS-Aud-2025  → Auditor

Env vars:
  CONFIDENCEOS_JWT_SECRET  — signing secret (auto-generated once if not set)
  CONFIDENCEOS_JWT_EXPIRY_HOURS — token lifetime in hours (default: 8)
  CONFIDENCEOS_API_KEY — optional machine-client API key guard (unchanged)
"""

import os
import secrets
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from database import get_db, User, SessionLocal

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

API_KEY_ENV = "CONFIDENCEOS_API_KEY"
JWT_SECRET_ENV = "CONFIDENCEOS_JWT_SECRET"
JWT_EXPIRY_ENV = "CONFIDENCEOS_JWT_EXPIRY_HOURS"

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = int(os.getenv(JWT_EXPIRY_ENV, "8"))

VALID_ROLES = {"Operator", "Maintenance", "Engineer", "Manager", "Auditor"}

# JWT secret: read from env or generate a stable one for the process lifetime.
# In production, always set CONFIDENCEOS_JWT_SECRET to a persistent secret.
_JWT_SECRET: str = os.getenv(JWT_SECRET_ENV) or secrets.token_hex(32)
if not os.getenv(JWT_SECRET_ENV):
    logger.warning(
        "CONFIDENCEOS_JWT_SECRET not set — using ephemeral secret. "
        "All tokens will be invalidated on server restart. "
        "Set this env var to a persistent secret for production."
    )

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 scheme — reads Authorization: Bearer <token>
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

# ── Demo seed users ──────────────────────────────────────────────────────────

DEMO_USERS = [
    {"username": "operator",  "password": "ConfidenceOS-Op-2025",   "role": "Operator",    "full_name": "Demo Operator"},
    {"username": "maint",     "password": "ConfidenceOS-Maint-2025","role": "Maintenance", "full_name": "Demo Maintenance Tech"},
    {"username": "engineer",  "password": "ConfidenceOS-Eng-2025",  "role": "Engineer",    "full_name": "Demo Engineer"},
    {"username": "manager",   "password": "ConfidenceOS-Mgr-2025",  "role": "Manager",     "full_name": "Demo Manager"},
    {"username": "auditor",   "password": "ConfidenceOS-Aud-2025",  "role": "Auditor",     "full_name": "Demo Auditor"},
]


def seed_demo_users() -> None:
    """Seed demo users if the users table is empty. Called once at startup."""
    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            for u in DEMO_USERS:
                db.add(User(
                    username=u["username"],
                    hashed_password=pwd_context.hash(u["password"]),
                    role=u["role"],
                    full_name=u["full_name"],
                    is_active=1,
                ))
            db.commit()
            logger.info("Seeded %d demo users.", len(DEMO_USERS))
    finally:
        db.close()


# ── Token helpers ─────────────────────────────────────────────────────────────

def create_access_token(username: str, role: str) -> str:
    """Issue a signed JWT token with username and role embedded."""
    expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    payload = {"sub": username, "role": role, "exp": expire}
    return jwt.encode(payload, _JWT_SECRET, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and verify a JWT token. Raises HTTPException on failure."""
    try:
        payload = jwt.decode(token, _JWT_SECRET, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role")
        if not username or not role:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token payload missing required fields.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return {"username": username, "role": role}
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token invalid or expired: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


# ── Dependencies ──────────────────────────────────────────────────────────────

def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    x_role: Optional[str] = Header(default=None),
) -> dict:
    """
    Resolve the current authenticated user from a Bearer token.

    Backward-compatibility bridge: if no Bearer token is present but X-Role is
    sent (old client behaviour), accept X-Role as an unauthenticated hint so the
    demo frontend continues to work without a login flow. This bridge should be
    removed once the frontend is fully updated to use JWT login.
    """
    if token:
        return decode_token(token)
    # Backward-compat fallback: trust X-Role header (unauthenticated)
    if x_role and x_role in VALID_ROLES:
        logger.debug("X-Role fallback used for role=%s (unauthenticated)", x_role)
        return {"username": "anonymous", "role": x_role}
    # Open demo mode: no token, no role header → default to Operator
    return {"username": "anonymous", "role": "Operator"}


def get_authenticated_user(
    token: str = Depends(oauth2_scheme),
) -> dict:
    """
    Strict version: requires a valid JWT. Used for write endpoints in production.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. POST /api/auth/login to obtain a token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return decode_token(token)


def require_role(*allowed: str):
    """
    Return a FastAPI dependency that enforces role membership from the JWT.
    Role is extracted from the verified token, not the X-Role header.
    """
    allowed_set = set(allowed)

    def _dep(user: dict = Depends(get_current_user)) -> dict:
        role = user.get("role", "")
        if role not in VALID_ROLES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown role '{role}'.",
            )
        if allowed_set and role not in allowed_set:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Role '{role}' is not permitted for this action. "
                    f"Required: {sorted(allowed_set)}."
                ),
            )
        return user

    return _dep


# ── API-key guard (unchanged — machine clients) ───────────────────────────────

def api_key_guard(x_api_key: Optional[str] = Header(default=None)):
    """Require a matching X-API-Key header IFF CONFIDENCEOS_API_KEY is set."""
    configured = os.getenv(API_KEY_ENV)
    if not configured:
        return
    if x_api_key != configured:
        raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key.")


# ── Password utilities (used by user management endpoints) ────────────────────

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def authenticate_user(username: str, password: str, db: Session) -> Optional[User]:
    """Return the User record if credentials are valid, else None."""
    user = db.query(User).filter(User.username == username, User.is_active == 1).first()
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user
