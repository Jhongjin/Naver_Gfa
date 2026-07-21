"""네이버 로그인 OAuth2 액세스 토큰 매니저.

관리계정 소유자가 최초 1회 네이버 로그인으로 refresh_token 을 발급받아 두면
(tools.get_refresh_token), 이후에는 refresh_token 으로 access_token 을 자동 갱신한다.
발급받은 access_token 은 ad-api 호출 시 `Authorization: Bearer {token}` 로 사용.
"""
from __future__ import annotations

import time

import httpx

from ..config import settings


class NaverTokenManager:
    def __init__(self) -> None:
        self._access_token: str | None = None
        self._expires_at: float = 0.0  # time.monotonic() 기준

    async def get_access_token(self, client: httpx.AsyncClient) -> str:
        # 만료 60초 전에 선제 갱신
        if self._access_token and time.monotonic() < self._expires_at - 60:
            return self._access_token
        return await self._refresh(client)

    async def _refresh(self, client: httpx.AsyncClient) -> str:
        if not settings.naver_refresh_token:
            raise RuntimeError(
                "NAVER_REFRESH_TOKEN 미설정 — tools.get_refresh_token 으로 먼저 발급하세요."
            )
        resp = await client.post(
            settings.naver_token_url,
            params={
                "grant_type": "refresh_token",
                "client_id": settings.naver_client_id,
                "client_secret": settings.naver_client_secret,
                "refresh_token": settings.naver_refresh_token,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        if "access_token" not in data:
            raise RuntimeError(f"토큰 갱신 실패: {data}")
        self._access_token = data["access_token"]
        self._expires_at = time.monotonic() + int(data.get("expires_in", 3600))
        return self._access_token
