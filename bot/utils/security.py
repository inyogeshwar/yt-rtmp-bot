"""
Security helpers: admin checks, token masking, stream-key encryption.
"""
from __future__ import annotations

import base64
import hashlib
from typing import Union

from cryptography.fernet import Fernet
from aiogram.types import Message, CallbackQuery

from config import ADMIN_IDS


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def require_admin(user_id: int) -> bool:
    """Raise PermissionError if not admin."""
    if not is_admin(user_id):
        raise PermissionError("⛔ Admin access required.")
    return True


def mask_key(key: str, visible: int = 4) -> str:
    """Show only last `visible` chars of a stream key."""
    if len(key) <= visible:
        return "****"
    return "*" * (len(key) - visible) + key[-visible:]


def simple_encrypt(text: str, secret: str) -> str:
    """Authenticated encryption for DB storage using Fernet."""
    # Derive a compatible 32-byte key from the secret
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    f = Fernet(key)
    return f.encrypt(text.encode()).decode()


def simple_decrypt(token: str, secret: str) -> str:
    """Decrypt a token using the same secret/key (with XOR fallback)."""
    # 1. Try Fernet
    try:
        key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
        f = Fernet(key)
        return f.decrypt(token.encode()).decode()
    except Exception:
        pass

    # 2. Try legacy XOR
    try:
        key_bytes = hashlib.sha256(secret.encode()).digest()
        data      = base64.urlsafe_b64decode(token.encode())
        dec       = bytes(b ^ key_bytes[i % 32] for i, b in enumerate(data))
        return dec.decode()
    except Exception:
        return token # Likely plain text or corrupted
