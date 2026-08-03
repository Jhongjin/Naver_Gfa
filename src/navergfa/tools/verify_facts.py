"""저장값 검증 — 우리 DB(report_facts) vs 네이버 성과 API 재조회 대조.

"중계 과정에서 값이 틀어졌는가"를 판정하는 도구. 네이버 어드민 CSV 와의 차이는
우리 계층 밖(네이버 내부 소스 간 차이)이므로 이 도구로는 알 수 없다.

실행:
  python -m src.navergfa.tools.verify_facts --account 57834 --from 2026-07-01 --to 2026-07-30
  python -m src.navergfa.tools.verify_facts --all --days 30      # 활성 키의 모든 계정
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import date, datetime, timedelta

from sqlalchemy import text

from ..config import settings
from ..db.engine import account_scoped_connection, engine
from ..naver.client import NaverAdApiClient
from ..naver.reports import fetch_performance

_RATE_DELAY = 1.1
_TOL = 1.0  # 반올림 허용 오차


def _targets(account: int | None) -> list[dict]:
    with engine.begin() as conn:
        if account:
            rows = conn.execute(
                text(
                    "SELECT naver_account_no, manager_account_no FROM naver_accounts "
                    "WHERE naver_account_no = :n"
                ),
                {"n": account},
            ).mappings().all()
        else:
            rows = conn.execute(
                text(
                    "SELECT DISTINCT ka.naver_account_no, na.manager_account_no "
                    "FROM key_accounts ka "
                    "JOIN api_keys k ON k.id = ka.api_key_id AND k.status='active' "
                    "LEFT JOIN naver_accounts na ON na.naver_account_no = ka.naver_account_no"
                )
            ).mappings().all()
        return [dict(r) for r in rows]


async def verify(account: int | None, d1: date, d2: date) -> int:
    accounts = _targets(account)
    total_cmp = 0
    mismatches: list[str] = []

    async with NaverAdApiClient() as client:
        for acc in accounts:
            no = acc["naver_account_no"]
            amn = acc.get("manager_account_no") or settings.naver_manager_account_no
            cur = d1
            api: dict[tuple, tuple] = {}
            while cur <= d2:  # 31일 청크
                stop = min(cur + timedelta(days=30), d2)
                try:
                    rows = await fetch_performance(
                        client, no, "campaign", cur, stop, amn, page_delay=_RATE_DELAY
                    )
                except Exception as e:  # noqa: BLE001
                    mismatches.append(f"[{no}] API 조회 실패 {cur}~{stop}: {e}")
                    rows = []
                for r in rows:
                    if not r.get("targetDate") or not r.get("campaignNo"):
                        continue
                    api[(str(r["targetDate"]), int(r["campaignNo"]))] = (
                        int(r.get("impCount") or 0),
                        int(r.get("clickCount") or 0),
                        float(r.get("sales") or 0),
                    )
                cur = stop + timedelta(days=1)

            with account_scoped_connection([no]) as conn:
                db_rows = conn.execute(
                    text(
                        "SELECT stat_date, campaign_id, impressions, clicks, cost "
                        "FROM report_facts WHERE naver_account_no=:n AND level='campaign' "
                        "AND stat_date BETWEEN :d1 AND :d2"
                    ),
                    {"n": no, "d1": d1, "d2": d2},
                ).mappings().all()
            db = {
                (r["stat_date"].isoformat(), int(r["campaign_id"])): (
                    int(r["impressions"]), int(r["clicks"]), float(r["cost"])
                )
                for r in db_rows
            }

            for k in sorted(set(api) | set(db)):
                total_cmp += 1
                a, b = api.get(k), db.get(k)
                if a is None:
                    mismatches.append(f"[{no}] {k[0]} c{k[1]}: DB에만 존재 {b}")
                elif b is None:
                    mismatches.append(f"[{no}] {k[0]} c{k[1]}: API에만 존재 {a}")
                elif (a[0] != b[0] or a[1] != b[1] or abs(a[2] - b[2]) > _TOL):
                    mismatches.append(
                        f"[{no}] {k[0]} c{k[1]}: API(노출{a[0]}/클릭{a[1]}/비용{a[2]:.2f}) "
                        f"!= DB(노출{b[0]}/클릭{b[1]}/비용{b[2]:.2f})"
                    )

    print(f"대조 완료: {len(accounts)}개 계정 · {total_cmp}건 비교")
    if mismatches:
        print(f"불일치 {len(mismatches)}건:")
        for m in mismatches[:50]:
            print("  -", m)
    else:
        print("불일치 0건: 저장값이 네이버 API 응답과 100% 일치합니다.")
    return len(mismatches)


def main() -> None:
    p = argparse.ArgumentParser(description="DB vs 네이버 API 저장값 대조")
    p.add_argument("--account", type=int, default=None)
    p.add_argument("--all", action="store_true", help="활성 키의 모든 계정")
    p.add_argument("--from", dest="d1", default=None, help="YYYY-MM-DD")
    p.add_argument("--to", dest="d2", default=None, help="YYYY-MM-DD")
    p.add_argument("--days", type=int, default=30)
    a = p.parse_args()

    d2 = datetime.strptime(a.d2, "%Y-%m-%d").date() if a.d2 else date.today() - timedelta(days=1)
    d1 = datetime.strptime(a.d1, "%Y-%m-%d").date() if a.d1 else d2 - timedelta(days=a.days - 1)
    asyncio.run(verify(None if a.all else a.account, d1, d2))


if __name__ == "__main__":
    main()
