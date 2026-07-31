"""수집 배치 진입점.

- 기본: 관리계정 트리에서 광고계정을 발견해 naver_accounts 에 upsert.
- --reports: 배정된(advertiser_id 있음) 계정의 캠페인 성과를 report_facts 에 적재.

실행:
  python -m src.navergfa.collector.run                 # 계정 트리 동기화
  python -m src.navergfa.collector.run --reports        # 성과 수집(최근 7일)
  python -m src.navergfa.collector.run --reports --days 31
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import date, timedelta

from sqlalchemy import text

from ..config import settings
from ..db.engine import account_scoped_connection, engine
from ..naver.accounts import extract_ad_accounts, fetch_manager_account_tree
from ..naver.client import NaverAdApiClient
from ..naver.reports import fetch_campaign_performance, to_fact

# 네이버 관리계정 한도 60회/분 → 호출 간 최소 간격(초)
_RATE_DELAY = 1.1

_UPSERT_FACT = text(
    """
    INSERT INTO report_facts
        (naver_account_no, stat_date, campaign_id, ad_group_id, ad_id,
         impressions, clicks, cost, conversions, conv_value, updated_at)
    VALUES
        (:naver_account_no, :stat_date, :campaign_id, :ad_group_id, :ad_id,
         :impressions, :clicks, :cost, :conversions, :conv_value, now())
    ON CONFLICT (naver_account_no, stat_date, campaign_id, ad_id) DO UPDATE SET
        impressions = EXCLUDED.impressions,
        clicks      = EXCLUDED.clicks,
        cost        = EXCLUDED.cost,
        conversions = EXCLUDED.conversions,
        conv_value  = EXCLUDED.conv_value,
        ad_group_id = EXCLUDED.ad_group_id,
        updated_at  = now()
    """
)


async def sync_accounts() -> list[dict]:
    """관리계정 하위 광고계정을 발견해 등록한다."""
    async with NaverAdApiClient() as client:
        tree = await fetch_manager_account_tree(
            client, settings.naver_manager_account_no
        )
    accounts = extract_ad_accounts(tree)

    with engine.begin() as conn:
        for acc in accounts:
            conn.execute(
                text(
                    """
                    INSERT INTO naver_accounts
                           (naver_account_no, account_name,
                            manager_account_no, manager_account_name, updated_at)
                    VALUES (:no, :name, :mno, :mname, now())
                    ON CONFLICT (naver_account_no) DO UPDATE
                       SET manager_account_no   = EXCLUDED.manager_account_no,
                           manager_account_name = EXCLUDED.manager_account_name,
                           updated_at           = now()
                    """
                ),
                {
                    "no": acc["naver_account_no"],
                    "name": acc.get("account_name"),
                    "mno": acc.get("manager_account_no"),
                    "mname": acc.get("manager_account_name"),
                },
            )
        conn.execute(
            text(
                "INSERT INTO collector_runs (job, started_at, finished_at, rows_upserted, status) "
                "VALUES ('accounts', now(), now(), :n, 'ok')"
            ),
            {"n": len(accounts)},
        )
    return accounts


def _date_chunks(start: date, end: date, size: int = 31):
    """네이버 성과 API는 한 번에 최대 31일 → 기간을 청크로 분할."""
    cur = start
    while cur <= end:
        stop = min(cur + timedelta(days=size - 1), end)
        yield cur, stop
        cur = stop + timedelta(days=1)


_UPSERT_STATE = text(
    """
    INSERT INTO account_sync_state (naver_account_no, backfilled_from, last_collected_to, updated_at)
    VALUES (:no, :start, :end, now())
    ON CONFLICT (naver_account_no) DO UPDATE SET
        last_collected_to = GREATEST(
            COALESCE(account_sync_state.last_collected_to, EXCLUDED.last_collected_to),
            EXCLUDED.last_collected_to),
        backfilled_from = LEAST(
            COALESCE(account_sync_state.backfilled_from, EXCLUDED.backfilled_from),
            EXCLUDED.backfilled_from),
        updated_at = now()
    """
)


async def sync_reports(days: int = 7, backfill_days: int = 90) -> int:
    """활성 키에 스코프된 광고계정의 캠페인 성과(일별)를 적재.

    - 대상: 활성 키가 참조하는 계정만(전체 2110이 아님) → 한도·시간 절약.
    - **신규 계정 자동 백필**: 수집 이력이 없으면 backfill_days 만큼 소급 수집.
    - **갭 자동 복구**: 마지막 수집일이 오래됐으면 그 지점부터 다시 수집.
    - 31일 초과 구간은 청크로 분할 호출(네이버 제약).
    - 네이버 한도(관리계정 60회/분) 준수: 호출마다 _RATE_DELAY 대기.
    """
    import asyncio

    end = date.today() - timedelta(days=1)  # 전일까지
    floor = end - timedelta(days=max(backfill_days - 1, 0))  # 소급 상한

    with engine.begin() as conn:
        accounts = [
            dict(r)
            for r in conn.execute(
                text(
                    """
                    SELECT DISTINCT ka.naver_account_no, na.manager_account_no,
                           s.last_collected_to, s.backfilled_from
                      FROM key_accounts ka
                      JOIN api_keys k ON k.id = ka.api_key_id AND k.status = 'active'
                      LEFT JOIN naver_accounts na ON na.naver_account_no = ka.naver_account_no
                      LEFT JOIN account_sync_state s ON s.naver_account_no = ka.naver_account_no
                    """
                )
            ).mappings()
        ]

    total = 0
    async with NaverAdApiClient() as client:
        for acc in accounts:
            no = acc["naver_account_no"]
            amn = acc.get("manager_account_no") or settings.naver_manager_account_no
            last_to = acc.get("last_collected_to")
            filled_from = acc.get("backfilled_from")

            if last_to is None or filled_from is None or filled_from > floor:
                # 신규 계정 또는 소급 미완료 → 백필 구간 전체 수집(1회)
                start = floor
            else:
                # 최소 days일 재수집(정산 보정) + 마지막 수집 이후 갭 복구
                start = min(end - timedelta(days=max(days - 1, 0)),
                            last_to - timedelta(days=2))
            start = max(start, floor)
            if start > end:
                continue

            acc_rows = 0
            failed = False
            for c_start, c_end in _date_chunks(start, end):
                try:
                    rows = await fetch_campaign_performance(
                        client, no, c_start, c_end, amn, page_delay=_RATE_DELAY
                    )
                except Exception as e:  # noqa: BLE001
                    failed = True
                    with engine.begin() as conn:
                        conn.execute(
                            text(
                                "INSERT INTO collector_runs (job, naver_account_no, started_at, "
                                "finished_at, status, error) VALUES "
                                "('reports', :no, now(), now(), 'error', :err)"
                            ),
                            {"no": no, "err": f"{c_start}~{c_end}: {e}"[:500]},
                        )
                    await asyncio.sleep(_RATE_DELAY)
                    break

                facts = [
                    to_fact(r, no, None)
                    for r in rows
                    if r.get("targetDate") and r.get("campaignNo")
                ]
                if facts:
                    with account_scoped_connection([no]) as conn:
                        for f in facts:
                            f.pop("advertiser_id", None)
                            conn.execute(_UPSERT_FACT, f)
                    acc_rows += len(facts)

            if not failed:
                # 성과 0건이어도 "그 기간은 수집했다"는 사실을 기록해야 재수집 폭주를 막는다
                with engine.begin() as conn:
                    conn.execute(_UPSERT_STATE, {"no": no, "start": start, "end": end})
            total += acc_rows

    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO collector_runs (job, started_at, finished_at, rows_upserted, status) "
                "VALUES ('reports', now(), now(), :n, 'ok')"
            ),
            {"n": total},
        )
    return total


def main() -> None:
    p = argparse.ArgumentParser(description="네이버 GFA 수집 배치")
    p.add_argument("--reports", action="store_true", help="성과 수집(미지정 시 계정 트리 동기화)")
    p.add_argument("--days", type=int, default=7, help="정기 재수집 일수(정산 보정용, 최대 31)")
    p.add_argument("--backfill-days", type=int, default=90,
                   help="신규 계정 소급 수집 일수(기본 90, 네이버 상한 2년)")
    args = p.parse_args()

    if args.reports:
        n = asyncio.run(sync_reports(min(args.days, 31), args.backfill_days))
        print(f"성과 적재 완료: {n}행 upsert")
    else:
        accounts = asyncio.run(sync_accounts())
        print(f"발견·등록된 광고계정: {len(accounts)}개")
        for a in accounts[:20]:
            print(f"  - {a['naver_account_no']}  {a.get('account_name') or ''}")
        print("\n(운영자: tools.issue_key 로 광고주에 배정하세요)")


if __name__ == "__main__":
    main()
