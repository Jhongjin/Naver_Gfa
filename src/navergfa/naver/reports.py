"""성과(리포트) 수집 — 네이버 성과 API.

스펙(가이드 확인):
  과거 성과   GET /adAccounts/{no}/performance/past/{aggregationType}
  전환 성과   GET /adAccounts/{no}/performance/conversion/past/{aggregationType}
  aggregationType = campaigns | adSets | creatives
  파라미터: startDate, endDate (yyyy-MM-dd, 최대 31일), timeUnit=daily|hourly(전환은 daily만),
           limit(<=1000), next(페이징 토큰)
  백필: 2년 전 ~ 전일 (전일은 당일 02:00 이후). 동기 응답.
  헤더: AccessManagerAccountNo (선택)
  응답 래퍼: {"rows": [...], "next": ...}
  필드: impCount, clickCount, convCount, convSales, sales(=광고비), vplayCount,
        campaignNo/adSetNo/creativeNo, targetDate, hour, updatedAt, convType(전환 조회 시)
"""
from __future__ import annotations

import asyncio
from datetime import date
from typing import Any

from .client import NaverAdApiClient

_LIST_KEYS = ("rows", "content", "data", "contents", "elements", "list", "records", "performances", "results")

# 내부 레벨명 ↔ 네이버 aggregationType
LEVEL_TO_AGG = {"campaign": "campaigns", "adset": "adSets", "creative": "creatives"}
# 세밀도 사다리: 상위 레벨을 선택하면 하위 레벨까지 모두 수집
GRANULARITY_LEVELS = {
    "campaign": ["campaign"],
    "adset": ["campaign", "adset"],
    "creative": ["campaign", "adset", "creative"],
}


def unwrap(data: Any) -> tuple[list[dict], str | None]:
    """응답에서 (레코드 리스트, next 토큰) 추출."""
    if isinstance(data, list):
        return data, None
    if isinstance(data, dict):
        nxt = data.get("next") or None
        for k in _LIST_KEYS:
            v = data.get(k)
            if isinstance(v, list):
                return v, nxt
    return [], None


async def _fetch_paged(
    client: NaverAdApiClient,
    path: str,
    start_date: date,
    end_date: date,
    manager_account_no: int | None,
    time_unit: str,
    page_delay: float,
) -> list[dict]:
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


async def fetch_performance(
    client: NaverAdApiClient,
    ad_account_no: int,
    level: str,
    start_date: date,
    end_date: date,
    manager_account_no: int | None = None,
    page_delay: float = 0.0,
) -> list[dict]:
    """레벨별 과거 성과(일별). level = campaign | adset | creative."""
    agg = LEVEL_TO_AGG[level]
    return await _fetch_paged(
        client,
        f"/adAccounts/{ad_account_no}/performance/past/{agg}",
        start_date, end_date, manager_account_no, "daily", page_delay,
    )


async def fetch_conversion(
    client: NaverAdApiClient,
    ad_account_no: int,
    level: str,
    start_date: date,
    end_date: date,
    manager_account_no: int | None = None,
    page_delay: float = 0.0,
) -> list[dict]:
    """레벨별 전환 성과(전환 타입 breakdown). 일별만 지원."""
    agg = LEVEL_TO_AGG[level]
    return await _fetch_paged(
        client,
        f"/adAccounts/{ad_account_no}/performance/conversion/past/{agg}",
        start_date, end_date, manager_account_no, "daily", page_delay,
    )


# 하위호환: 기존 호출부(캠페인 단위)
async def fetch_campaign_performance(
    client: NaverAdApiClient,
    ad_account_no: int,
    start_date: date,
    end_date: date,
    manager_account_no: int | None = None,
    time_unit: str = "daily",
    page_delay: float = 0.0,
) -> list[dict]:
    return await fetch_performance(
        client, ad_account_no, "campaign", start_date, end_date,
        manager_account_no, page_delay,
    )


def _num(row: dict, *keys: str) -> Any:
    for k in keys:
        v = row.get(k)
        if v is not None:
            return v
    return 0


def to_fact(row: dict, ad_account_no: int, level: str = "campaign") -> dict:
    """성과 레코드 → report_facts 행.

    필드 확정(실데이터 검증): sales=광고비, convSales=전환매출, vplayCount=조회수.
    상위 레벨 조회 시 하위 식별자는 null → 0 으로 저장(PK NOT NULL).
    """
    return {
        "naver_account_no": ad_account_no,
        "level": level,
        "stat_date": row.get("targetDate"),
        "campaign_id": row.get("campaignNo") or 0,
        "ad_group_id": row.get("adSetNo") or 0,
        "ad_id": row.get("creativeNo") or 0,
        "impressions": int(_num(row, "impCount")),
        "clicks": int(_num(row, "clickCount")),
        "cost": _num(row, "sales"),
        "conversions": int(_num(row, "convCount")),
        "conv_value": _num(row, "convSales"),
        "views": int(_num(row, "vplayCount")),
    }


def to_conversion_fact(row: dict, ad_account_no: int, level: str) -> dict:
    """전환 레코드 → conversion_facts 행."""
    return {
        "naver_account_no": ad_account_no,
        "level": level,
        "stat_date": row.get("targetDate"),
        "campaign_id": row.get("campaignNo") or 0,
        "ad_group_id": row.get("adSetNo") or 0,
        "ad_id": row.get("creativeNo") or 0,
        "conv_type": str(row.get("convType") or "UNKNOWN"),
        "conversions": int(_num(row, "convCount")),
        "conv_value": _num(row, "convSales"),
    }
