"""Encryption at rest for QuickBooks OAuth tokens.

Intuit's Developer Terms require protecting customer credentials; tokens are stored with
Fernet (AES-128 + HMAC). Key: TOKEN_ENCRYPTION_KEY (a Fernet key); when it is not set, a key
is derived from SECRET_KEY so existing deployments keep working.
"""

from __future__ import annotations

import base64
import hashlib
import logging
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from app.core.config import get_settings

logger = logging.getLogger(__name__)
_FERNET_PREFIX = "gAAAAA"  # every Fernet token starts with the version byte 0x80


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    settings = get_settings()
    key = settings.token_encryption_key
    if not key:
        if settings.secret_key.startswith("change-me"):
            logger.warning("TOKEN_ENCRYPTION_KEY and SECRET_KEY are not set: tokens use a weak key")
        key = base64.urlsafe_b64encode(hashlib.sha256(settings.secret_key.encode()).digest())
    return Fernet(key)


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    """Plain values stored before encryption existed are returned as they are."""
    if not value.startswith(_FERNET_PREFIX):
        return value
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        logger.error("Stored token cannot be decrypted with the current key")
        raise


class EncryptedText(TypeDecorator):
    """Text column encrypted on write and decrypted on read."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return None if value is None else encrypt(value)

    def process_result_value(self, value, dialect):
        return None if value is None else decrypt(value)
