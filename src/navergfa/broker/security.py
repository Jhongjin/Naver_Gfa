"""API 키 생성/해시.

발급 키 형식:  ngfa_<prefix8>.<secret>
저장은 HMAC-SHA256(pepper, full_key) 해시만. 원문은 발급 시 1회만 노출.
해시로 조회하므로 상수시간 비교가 필요 없고 인덱스 조회가 가능하다.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

from ..config import settings


def hash_api_key(full_key: str) -> str:
    return hmac.new(
        settings.api_key_pepper.encode("utf-8"),
        full_key.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def generate_api_key() -> tuple[str, str, str]:
    """returns (full_key, key_prefix, key_hash)."""
    prefix = "ngfa_" + secrets.token_hex(4)  # 8 hex chars
    secret = secrets.token_urlsafe(32)
    full = f"{prefix}.{secret}"
    return full, prefix, hash_api_key(full)
