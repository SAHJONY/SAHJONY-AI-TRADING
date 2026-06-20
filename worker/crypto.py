"""AES-256-GCM secret crypto — byte-compatible with the Next.js side (lib/crypto.ts).

Stored format: base64(iv) + "." + base64(ciphertext||tag).  iv is 12 bytes.
SECRET_ENCRYPTION_KEY is base64 of exactly 32 bytes (a 256-bit key), shared by
the web app (encrypts on entry) and this worker (decrypts at run time).
"""
from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _key() -> bytes:
    raw = os.environ.get("SECRET_ENCRYPTION_KEY", "")
    if not raw:
        raise RuntimeError("SECRET_ENCRYPTION_KEY is not set")
    key = base64.b64decode(raw)
    if len(key) != 32:
        raise ValueError("SECRET_ENCRYPTION_KEY must be base64 of exactly 32 bytes")
    return key


def encrypt(plaintext: str) -> str:
    iv = os.urandom(12)
    ct = AESGCM(_key()).encrypt(iv, plaintext.encode("utf-8"), None)
    return base64.b64encode(iv).decode() + "." + base64.b64encode(ct).decode()


def decrypt(token: str) -> str:
    iv_b64, ct_b64 = token.split(".", 1)
    iv = base64.b64decode(iv_b64)
    ct = base64.b64decode(ct_b64)
    return AESGCM(_key()).decrypt(iv, ct, None).decode("utf-8")
