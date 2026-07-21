"""네이버 GFA ad-api HTTP 클라이언트.

Base: https://openapi.naver.com/v1/ad-api/{version}
인증: Authorization: Bearer {access_token}
관리계정 하위 접근: AccessManagerAccountNo 헤더로 대상 지정.
"""
from __future__ import annotations

from typing import Any

import httpx

from ..config import settings
from .auth import NaverTokenManager


class NaverAdApiClient:
    def __init__(self, tokens: NaverTokenManager | None = None) -> None:
        self._tokens = tokens or NaverTokenManager()
        self._client = httpx.AsyncClient(timeout=30.0)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "NaverAdApiClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def get(
        self,
        path: str,
        *,
        access_manager_account_no: int | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        token = await self._tokens.get_access_token(self._client)
        headers = {"Authorization": f"Bearer {token}"}
        if access_manager_account_no is not None:
            headers["AccessManagerAccountNo"] = str(access_manager_account_no)
        resp = await self._client.get(
            f"{settings.api_prefix}{path}", headers=headers, params=params
        )
        resp.raise_for_status()
        return resp.json()
