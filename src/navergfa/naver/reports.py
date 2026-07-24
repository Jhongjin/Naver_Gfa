"""성과(리포트) 수집 — 네이버 성과 API.

스펙(2026-07-21 가이드 확인):
  GET /adAccounts/{adAccountNo}/performance/past/{aggregationType}
    aggregationType = campaigns | adSets | creatives
  파라미터: startDate, endDate (yyyy-MM-dd, 최대 31일), timeUnit=daily|hourly, limit(<=1000), next
  백필: 2년 전 ~ 전일 (전일은 당일 02:00 이후). 동기 응답.
  헤더: AccessManagerAccountNo (선택)
  응답 필드: impCount, clickCount, convCount, convSales, sales, vplayCount,
            campaignNo/adSetNo/creativeNo, targetDate, hour, updatedAt, next
"""
from __future__ import annotations

from datetime import date
from typing import Any

from .client import NaverAdApiClient

_LIST_KEYS = ("rows", "data", "contents", "elements", "list", "records", "performances", "results")


def unwrap(data: Any) -> tuple[list[dict], str | None]:
    """응답에서 (레코드 리스트, next 토큰) 추출. 래퍼 구조가 불확실해 방어적으로 처리."""
    if isinstance(data, list):
        return data, None
    if isinstance(data, dict):
        nxt = data.get("next") or None
        for k in _LIST_KEYS:
            v = data.get(k)
            if isinstance(v, list):
                return v, nxt
    return [], None


async def fetch_campaign_performance(
    client: NaverAdApiClient,
    ad_account_no: int,
    start_date: date,
    end_date: date,
    manager_account_no: int | None = None,
    time_unit: str = "daily",
    page_delay: float = 0.0,
) -> list[dict]:
    """캠페인 단위 과거 성과(일별). next 토큰 페이징 처리.

    page_delay: 각 HTTP 호출 후 대기(초) — 네이버 관리계정 60회/분 한도 준수용.
    """
    import asyncio

    path = f"/adAccounts/{ad_account_no}/performance/past/campaigns"
    base = {
        "startDate": start_date.isoformat(),
        "endDate": end_date.isoformat(),
        "timeUnit": time_unit,
        "limit": 1000,
    }
    params = dict(base)
    out: list[dict] = []
    for _ in range(10_000):  # 안전 상한
        data = await client.get(
            path, access_manager_account_no=manager_account_no, params=params
        )
        if page_delay:
            await asyncio.sleep(page_delay)
        batch, nxt = unwrap(data)
        out.extend(batch)
        if not nxt:
            break
        params = {**base, "next": nxt}
    return out


def _num(row: dict, *keys: str) -> Any:
    for k in keys:
        v = row.get(k)
        if v is not None:
            return v
    return 0


def to_fact(row: dict, ad_account_no: int, advertiser_id: int) -> dict:
    """성과 레코드 → report_facts 행.

    필드 확정(2026-07-21 실데이터): sales=광고비(CPC/CPM 기준 검증), convSales=전환매출.
    응답 래퍼는 {"rows": [...], "next": ...}. 캠페인 단위는 adSetNo/creativeNo=null → ad_id=0.
    """
    return {
        "advertiser_id": advertiser_id,
        "naver_account_no": ad_account_no,
        "stat_date": row.get("targetDate"),
        "campaign_id": row.get("campaignNo") or 0,
        "ad_group_id": row.get("adSetNo"),
        "ad_id": row.get("creativeNo") or 0,
        "impressions": int(_num(row, "impCount")),
        "clicks": int(_num(row, "clickCount")),
        "cost": _num(row, "sales"),
        "conversions": int(_num(row, "convCount")),
        "conv_value": _num(row, "convSales"),
    }
