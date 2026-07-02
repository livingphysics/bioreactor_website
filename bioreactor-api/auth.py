"""
Authentication and rate limiting for the Bioreactor API.

- Bearer token auth via API_KEY environment variable
- Rate limiting via slowapi (defaults to 100 req/min)
- Cloudflare-aware IP extraction
"""
import os
import logging
from typing import Optional

from fastapi import HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
API_KEY = os.getenv("API_KEY")
RATE_LIMIT = os.getenv("RATE_LIMIT", "100/minute")

if not API_KEY:
    logger.warning("API_KEY not set — authentication disabled (dev mode)")


# ---------------------------------------------------------------------------
# IP extraction (Cloudflare-aware)
# ---------------------------------------------------------------------------
def get_client_ip(request: Request) -> str:
    """
    Extract real client IP, preferring Cloudflare headers.

    Priority:
    1. CF-Connecting-IP (Cloudflare)
    2. X-Forwarded-For (first IP)
    3. request.client.host (direct connection)
    """
    # Cloudflare header
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip

    # Standard proxy header
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()

    # Direct connection
    return get_remote_address(request)


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------
limiter = Limiter(key_func=get_client_ip)


# ---------------------------------------------------------------------------
# Bearer token authentication
# ---------------------------------------------------------------------------
security = HTTPBearer(auto_error=False)


async def verify_token(request: Request) -> Optional[str]:
    """
    FastAPI dependency that verifies the Bearer token.

    - If API_KEY is not set, auth is skipped (dev mode)
    - If API_KEY is set, requests must include valid Authorization header
    """
    if not API_KEY:
        # Dev mode - no auth required
        return None

    credentials: Optional[HTTPAuthorizationCredentials] = await security(request)

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication scheme",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if credentials.credentials != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )

    return credentials.credentials
