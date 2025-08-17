from __future__ import annotations

import os
from typing import Any

from cryptography.fernet import Fernet
from sqlalchemy import LargeBinary
from sqlalchemy.types import TypeDecorator


def _get_fernet() -> Fernet:
    """Return a Fernet instance from PII_ENCRYPTION_KEY.

    The key must be a urlsafe base64-encoded 32-byte key. In dev, generate one with:
      python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    """
    key = os.getenv("PII_ENCRYPTION_KEY") or os.getenv("ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("PII_ENCRYPTION_KEY is required to encrypt/decrypt sensitive fields.")
    return Fernet(key.encode() if isinstance(key, str) else key)


class EncryptedString(TypeDecorator[str]):
    """Transparent string encryption using Fernet (symmetric AES/GCM).

    Stores ciphertext bytes; SQL type is LargeBinary for portability.
    """

    impl = LargeBinary
    cache_ok = True

    def process_bind_param(self, value: Any, dialect):  # type: ignore[override]
        if value is None:
            return None
        f = _get_fernet()
        data = value.encode("utf-8") if isinstance(value, str) else bytes(value)
        token = f.encrypt(data)
        return token

    def process_result_value(self, value: Any, dialect):  # type: ignore[override]
        if value is None:
            return None
        f = _get_fernet()
        try:
            token = bytes(value)
            decrypted = f.decrypt(token)
            return decrypted.decode("utf-8")
        except Exception:
            # In case legacy values were stored as plain text, return as-is
            try:
                return value.decode("utf-8")  # type: ignore[no-any-return]
            except Exception:
                return str(value)
