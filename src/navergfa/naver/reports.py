"""리포트/통계 수집.

⛔ STUB — 네이버 리포트/통계 API 스펙 미확인.
가이드의 stat/report 문서(또는 파트너 회신)로 아래를 확정한 뒤 구현한다:
  - 엔드포인트 경로/메서드, 요청 파라미터(기간·집계단위·지표)
  - 응답 필드명(impressions/clicks/cost/conversions/…)
  - 소급(백필) 가능 기간, 비동기 리포트 여부(요청→폴링 다운로드 방식일 수 있음)

호출 형태는 계정 API와 동일: GET /{v}/... 에 AccessManagerAccountNo 헤더 지정.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from .client import NaverAdApiClient


async def fetch_report(
    client: NaverAdApiClient,
    ad_account_no: int,
    date_from: date,
    date_to: date,
    manager_account_no: int,
) -> list[dict[str, Any]]:
    raise NotImplementedError(
        "리포트 API 스펙 미확인. 가이드의 stat/report 문서 확인 후 구현하세요. "
        "확정 시 report_facts 스키마(impressions/clicks/cost/conversions/conv_value)에 매핑."
    )
