"""성과 API 응답 검증 (DB 쓰기 없음).

배정된 계정 하나를 골라 최근 성과를 조회하고, 원시 응답 구조와 매핑 결과를 출력한다.
sales(비용/매출) 및 래퍼 구조 확인용.

실행: python -m src.navergfa.tools.probe_report [--account 230] [--days 7]
"""
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date, timedelta

from sqlalchemy import text

from ..config import settings
from ..db.engine import engine
from ..naver.client import NaverAdApiClient
from ..naver.reports import to_fact, unwrap


async def main(account: int | None, days: int) -> None:
    with engine.begin() as conn:
        if account is None:
            row = conn.execute(
                text(
                    "SELECT naver_account_no, advertiser_id, manager_account_no "
                    "FROM naver_accounts WHERE advertiser_id IS NOT NULL "
                    "ORDER BY naver_account_no LIMIT 1"
                )
            ).mappings().first()
        else:
            row = conn.execute(
                text(
                    "SELECT naver_account_no, advertiser_id, manager_account_no "
                    "FROM naver_accounts WHERE naver_account_no = :no"
                ),
                {"no": account},
            ).mappings().first()

    if not row:
        print("대상 계정 없음 (issue_key 로 배정된 계정이 필요).")
        return

    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=days - 1)
    amn = row.get("manager_account_no") or settings.naver_manager_account_no
    no = row["naver_account_no"]
    path = f"/adAccounts/{no}/performance/past/campaigns"
    print(f"조회: 계정 {no}, {start}~{end}, campaigns/daily")

    async with NaverAdApiClient() as client:
        raw = await client.get(
            path,
            access_manager_account_no=amn,
            params={"startDate": start.isoformat(), "endDate": end.isoformat(),
                    "timeUnit": "daily", "limit": 1000},
        )

    print("\n=== 원시 응답(앞부분) ===")
    print(json.dumps(raw, ensure_ascii=False, indent=2)[:1200])

    batch, nxt = unwrap(raw)
    print(f"\n=== unwrap: {len(batch)}개 레코드, next={nxt!r} ===")
    if batch:
        print("첫 레코드:", json.dumps(batch[0], ensure_ascii=False))
        print("매핑 결과:", json.dumps(to_fact(batch[0], no, row["advertiser_id"]),
                                    ensure_ascii=False, default=str))
    print("\n(원시 응답의 필드/구조를 공유해 주시면 매핑을 확정합니다.)")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--account", type=int, default=None)
    p.add_argument("--days", type=int, default=7)
    args = p.parse_args()
    asyncio.run(main(args.account, args.days))
