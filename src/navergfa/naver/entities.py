"""엔티티(캠페인/광고그룹/소재) 이름 조회 — 관리(AD_MANAGEMENT) API.

  GET /adAccounts/{no}/campaigns   (page, size<=100)  → campaignNo, name
  GET /adAccounts/{no}/adSets      (page, size<=100)  → adSetNo,   name
  GET /adAccounts/{no}/creatives   (page, size<=100)  → creativeNo, name

광고주가 campaign_id 만 받으면 무슨 캠페인인지 알 수 없으므로 이름을 함께 제공한다.
"""
from __future__ import annotations

import asyncio
from typing import Any

from .client import NaverAdApiClient
from .reports import unwrap

# 내부 레벨명 → (경로 세그먼트, 식별자 필드)
# 관리 API 응답은 래퍼 "content", 식별자는 "no" (성과 API 의 campaignNo/adSetNo/creativeNo 와 다름)
ENTITY_SPEC = {
    "campaign": ("campaigns", ("no", "campaignNo")),
    "adset": ("adSets", ("no", "adSetNo")),
    "creative": ("creatives", ("no", "creativeNo")),
}


async def fetch_entities(
    client: NaverAdApiClient,
    ad_account_no: int,
    level: str,
    manager_account_no: int | None = None,
    page_delay: float = 0.0,
    max_pages: int = 50,
) -> list[dict[str, Any]]:
    """레벨별 엔티티 목록 → [{entity_no, name}]."""
    seg, id_fields = ENTITY_SPEC[level]
    path = f"/adAccounts/{ad_account_no}/{seg}"
    out: list[dict[str, Any]] = []
    for page in range(max_pages):
        data = await client.get(
            path,
            access_manager_account_no=manager_account_no,
            params={"page": page, "size": 100},
        )
        if page_delay:
            await asyncio.sleep(page_delay)
        batch, _ = unwrap(data)
        if not batch:
            break
        for r in batch:
            no = next((r.get(k) for k in id_fields if r.get(k) is not None), None)
            if no is None:
                continue
            try:
                out.append({"entity_no": int(no), "name": (r.get("name") or "").strip() or None})
            except (TypeError, ValueError):
                continue
        if len(batch) < 100:
            break
    return out
