"""
auth.py — Lightweight, honest access control for ConfidenceOS.

This is NOT a full identity provider. It adds two reusable FastAPI dependencies:

  * `api_key_guard`   — when CONFIDENCEOS_API_KEY is set, mutating endpoints
                        require a matching `X-API-Key` header (else 401). When
                        the env var is unset (demo/dev) it is a no-op, so the
                        existing demo flow is unchanged.
  * `require_role(*)` — centralizes server-side role enforcement. The actor role
                        is read from the `X-Role` header (operator-asserted — no
                        real identity yet, honestly labelled). When the header is
                        absent it is permissive (back-compat); when present it is
                        enforced against the allowed set (else 403).

The read-only-to-plant contract is unaffected: these guards gate *who may call*
mutating endpoints; they never enable writing plant control commands.
"""

import os
from fastapi import Header, HTTPException

API_KEY_ENV = "CONFIDENCEOS_API_KEY"

VALID_ROLES = {"Operator", "Maintenance", "Engineer", "Manager", "Auditor"}


def api_key_guard(x_api_key: str | None = Header(default=None)):
    """Require a matching X-API-Key header IFF an API key is configured.

    No-op when CONFIDENCEOS_API_KEY is unset (demo/dev), so nothing breaks
    out of the box; enforcing the moment a key is provided.
    """
    configured = os.getenv(API_KEY_ENV)
    if not configured:
        return  # auth disabled — open demo mode
    if x_api_key != configured:
        raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key.")


def require_role(*allowed: str):
    """Return a dependency enforcing the actor role (from X-Role) is in `allowed`.

    Permissive when the header is absent (back-compat with clients that don't yet
    send it); enforcing when present. Role is operator-asserted, not authenticated.
    """
    allowed_set = set(allowed)

    def _dep(x_role: str | None = Header(default=None)):
        if x_role is None:
            return None  # back-compat: no header → defer to any in-endpoint check
        if x_role not in VALID_ROLES:
            raise HTTPException(status_code=400, detail=f"Unknown role '{x_role}'.")
        if allowed_set and x_role not in allowed_set:
            raise HTTPException(
                status_code=403,
                detail=f"Role '{x_role}' is not permitted here. Allowed: {sorted(allowed_set)}.",
            )
        return x_role

    return _dep
