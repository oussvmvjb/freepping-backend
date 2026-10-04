import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple
import jwt
from argon2 import PasswordHasher, Type
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError

from app.core.config import settings
from app.core.exceptions import AuthenticationException

# Initialize Argon2id password hasher with secure parameters
_ph = PasswordHasher(
    time_cost=2,
    memory_cost=19456,  # 19 MB
    parallelism=1,
    hash_len=32,
    type=Type.ID  # Argon2id variant
)


def hash_password(password: str) -> str:
    """Hashes a plaintext password using Argon2id."""
    if not password or len(password) < 8:
        raise ValueError("Password must be at least 8 characters long.")
    return _ph.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plaintext password against an Argon2id hash."""
    if not plain_password or not hashed_password:
        return False
    try:
        return _ph.verify(hashed_password, plain_password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def hash_token(raw_token: str) -> str:
    """Computes a SHA-256 cryptographic hash of the raw token for secure storage."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def create_access_token(user_id: uuid.UUID, role: str) -> Tuple[str, datetime]:
    """
    Creates a signed Access JWT.
    Claims: sub (user_id), role, type ('access'), iat, exp (15 mins), jti (uuid).
    """
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    token_id = str(uuid.uuid4())

    payload = {
        "sub": str(user_id),
        "role": role,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": token_id,
    }

    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token, expires_at


def create_refresh_token(user_id: uuid.UUID, session_id: uuid.UUID) -> Tuple[str, datetime]:
    """
    Creates a signed Refresh JWT.
    Claims: sub (user_id), type ('refresh'), iat, exp (7 days), jti (session_id).
    """
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": str(session_id),
    }

    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token, expires_at


def decode_token(token: str) -> Dict[str, Any]:
    """
    Decodes and validates a JWT token.
    Raises AuthenticationException on failure.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["sub", "type", "exp", "iat", "jti"]}
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise AuthenticationException("Token has expired.")
    except jwt.InvalidTokenError as e:
        raise AuthenticationException("Invalid token signature or claims.")
