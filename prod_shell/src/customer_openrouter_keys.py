"""Buyer-owned OpenRouter provider connection for the MACIE C pilot.

A customer connects a personal OpenRouter *completion* API key, not a
management key. Keys are never placed in the session cookie, an environment
variable, the shared router singleton, a GitHub repo, logs, or responses.

While this pilot uses one Render process, keys are encrypted in RAM and
expire at the end of the signed-in session. The commercial implementation
MUST replace this volatile dictionary with a durable encrypted per-tenant
vault and customer-managed revoke/rotation, before sales begin.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import threading
import time
from typing import Any

import httpx
from cryptography.fernet import Fernet, InvalidToken

_MAX_KEY_CHARS = 400
_TTL_SECONDS = 8 * 60 * 60
_LOCK = threading.RLock()
_KEYS: dict[str, tuple[float, bytes]] = {}


def _vault_cipher() -> Fernet:
    # The server session secret is not exposed through the browser cookie.
    secret = os.environ.get("MACIE_C_SESSION_SECRET", "")
    if len(secret) < 40:
        raise RuntimeError("The MACIE C credential vault is not configured.")
    derived = hashlib.sha256(b"macie-c-customer-vault-v1:" + secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(derived))


def _slot(account: str, session_id: str) -> str:
    if not account or not session_id:
        raise ValueError("An authenticated MACIE C session is required.")
    return hashlib.sha256((account + "\x00" + session_id).encode()).hexdigest()


def _validate_shape(key: str) -> None:
    if (
        not isinstance(key, str)
        or not key.startswith("sk-or-")
        or len(key) < 30
        or len(key) > _MAX_KEY_CHARS
        or not key.isascii()
        or any(c.isspace() or ord(c) < 33 or ord(c) > 126 for c in key)
    ):
        raise ValueError("Enter a valid OpenRouter completion API key.")


def verify_openrouter_key(key: str, *, client: Any = None) -> None:
    """Verify customer-supplied key using OpenRouter's official key endpoint.

    No text returned by the external provider is echoed to the browser or
    logs; the user key never appears in a URL/query string.
    """
    _validate_shape(key)
    transport = client if client is not None else httpx
    try:
        response = transport.get(
            "https://openrouter.ai/api/v1/key",
            headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
            timeout=12,
            follow_redirects=False,
        )
    except (httpx.HTTPError, OSError):
        raise ValueError("OpenRouter could not be reached. Try again later.") from None
    if response.status_code in (401, 403):
        raise ValueError("OpenRouter rejected this key. Check or replace it.")
    if response.status_code != 200:
        raise ValueError("OpenRouter could not validate the key right now.")
    try:
        details = response.json().get("data", {})
    except (ValueError, AttributeError):
        raise ValueError("OpenRouter returned an unexpected validation response.") from None
    if not isinstance(details, dict):
        raise ValueError("OpenRouter returned an unexpected validation response.")
    if details.get("is_management_key") or details.get("is_provisioning_key"):
        raise ValueError("Use a standard OpenRouter completion key, not a management key.")


def save_key(account: str, session_id: str, key: str, *, verify: bool = True) -> None:
    _validate_shape(key)
    if verify:
        verify_openrouter_key(key)
    encrypted = _vault_cipher().encrypt(key.encode("ascii"))
    with _LOCK:
        _KEYS[_slot(account, session_id)] = (time.monotonic() + _TTL_SECONDS, encrypted)
        _expire_locked()


def _expire_locked() -> None:
    now = time.monotonic()
    for slot, (expires_at, _blob) in list(_KEYS.items()):
        if expires_at < now:
            del _KEYS[slot]


def connected(account: str, session_id: str) -> bool:
    try:
        with _LOCK:
            _expire_locked()
            return _slot(account, session_id) in _KEYS
    except ValueError:
        return False


def get_key(account: str, session_id: str) -> str | None:
    try:
        with _LOCK:
            _expire_locked()
            row = _KEYS.get(_slot(account, session_id))
        if row is None:
            return None
        return _vault_cipher().decrypt(row[1]).decode("ascii")
    except (InvalidToken, ValueError, UnicodeDecodeError, RuntimeError):
        return None


def revoke(account: str, session_id: str) -> None:
    try:
        with _LOCK:
            _KEYS.pop(_slot(account, session_id), None)
    except ValueError:
        return


def clear_for_testing() -> None:
    with _LOCK:
        _KEYS.clear()
