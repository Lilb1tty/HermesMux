"""Small protocol helpers that do not depend on Hermes."""

from __future__ import annotations

import hashlib
import hmac


def valid_callback_signature(token: str, timestamp: str, nonce: str, signature: str) -> bool:
    """Validate WeChat's plaintext callback signature."""
    expected = hashlib.sha1("".join(sorted((token, timestamp, nonce))).encode()).hexdigest()
    return hmac.compare_digest(expected, signature)
