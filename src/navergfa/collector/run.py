"""수집 배치 진입점.

- 기본: 관리계정 트리에서 광고계정을 발견해 naver_accounts 에 upsert.
- --reports: 활성 키에 담긴 계정의 성과를 적재.
    · 계정별 수집 세밀도(naver_accounts.granularity)에 따라
      campaign / adset / creative 레벨을 수집(사다리식).
    · collect_conversions=true 면 전환 타입 breakdown 도 수집.
    · 신규 계정 자동 백필 + 갭 자동 복구 + 31일 청크 분할.
    · 엔티티(캠페인/광고그룹/소재) 이름은 주 1회 동기화.

실행:
  python -m src.navergfa.collector.run                  # 계정 트리 동기화
  python -m src.navergfa.collector.run --reports         # 성과 수집
  python -m src.navergfa.collector.run --reports --days 3 --backfill-days 90
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
from ..naver.entities import fetch_entities
from ..naver.reports import (
    GRANULARITY_LEVELS,
    fetch_conversion,
    fetch_performance,
    to_conversion_fact,
    to_fact,
)

# 네이버 관리계정 한도 60회/분 → 호출 간 최소 간격(초)
_RATE_DELAY = 1.1
# 엔티티 이름 재동기화 주기(일)
_ENTITY_TTL_DAYS = 7

_UPSERT_FACT = text(
    """
    INSERT INTO report_facts
        (naver_account_no, level, stat_date, campaign_id, ad_group_id, ad_id,
         impressions, clicks, cost, conversions, conv_value, views, updated_at)
    VALUES
        (:naver_account_no, :level, :stat_date, :campaign_id, :ad_group_id, :ad_id,
         :impressions, :clicks, :cost, :conversions, :conv_value, :views, now())
    ON CONFLICT (naver_account_no, stat_date, level, campaign_id, ad_group_id, ad_id) DO UPDATE SET
        impressions = EXCLUDED.impressions,
        clicks      = EXCLUDED.clicks,
        cost        = EXCLUDED.cost,
        conversions = EXCLUDED.conversions,
        conv_value  = EXCLUDED.conv_value,
        views       = EXCLUDED.views,
        updated_at  = now()
    """
)

_UPSERT_CONV = text(
    """
    INSERT INTO conversion_facts
        (naver_account_no, level, stat_date, campaign_id, ad_group_id, ad_id,
         conv_type, conversions, conv_value, updated_at)
    VALUES
        (:naver_account_no, :level, :stat_date, :campaign_id, :ad_group_id, :ad_id,
         :conv_type, :conversions, :conv_value, now())
    ON CONFLICT (naver_account_no, stat_date, level, campaign_id, ad_group_id, ad_id, conv_type)
    DO UPDATE SET
        conversions = EXCLUDED.conversions,
        conv_value  = EXCLUDED.conv_value,
        updated_at  = now()
    """
)

_UPSERT_ENTITY = text(
    """
    INSERT INTO ad_entities (naver_account_no, level, entity_no, name, updated_at)
    VALUES (:naver_account_no, :level, :entity_no, :name, now())
    ON CONFLICT (naver_account_no, level, entity_no) DO UPDATE SET
        name = EXCLUDED.name, updated_at = now()
    """
)

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


def _date_chunks(start: date, end: date, size: int = 31):
    """네이버 성과 API는 한 번에 최대 31일 → 기간을 청크로 분할."""
    cur = start
    while cur <= end:
        stop = min(cur + timedelta(days=size - 1), end)
        yield cur, stop
        cur = stop + timedelta(days=1)


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


def _log_error(no: int, msg: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO collector_runs (job, naver_account_no, started_at, "
                "finished_at, status, error) VALUES "
                "('reports', :no, now(), now(), 'error', :err)"
            ),
            {"no": no, "err": msg[:500]},
        )


async def _sync_entities(client, no: int, amn: int, levels: list[str]) -> None:
    """엔티티 이름 동기화(주 1회). 실패해도 성과 수집은 계속한다."""
    for level in levels:
        try:
            items = await fetch_entities(client, no, level, amn, page_delay=_RATE_DELAY)
        except Exception as e:  # noqa: BLE001
            _log_error(no, f"entities/{level}: {e}")
            continue
        if not items:
            continue
        with account_scoped_connection([no]) as conn:
            for it in items:
                conn.execute(
                    _UPSERT_ENTITY,
                    {
                        "naver_account_no": no,
                        "level": level,
                        "entity_no": it["entity_no"],
                        "name": it["name"],
                    },
                )
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE account_sync_state SET entities_synced_at = now() "
                "WHERE naver_account_no = :no"
            ),
            {"no": no},
        )


async def sync_reports(days: int = 7, backfill_days: int = 90) -> int:
    """활성 키에 담긴 계정의 성과를 계정별 세밀도에 맞춰 적재."""
    end = date.today() - timedelta(days=1)  # 전일까지
    floor = end - timedelta(days=max(backfill_days - 1, 0))  # 소급 상한

    with engine.begin() as conn:
        accounts = [
            dict(r)
            for r in conn.execute(
                text(
                    """
                    SELECT DISTINCT ka.naver_account_no, na.manager_account_no,
                           COALESCE(na.granularity, 'campaign')  AS granularity,
                           COALESCE(na.collect_conversions,false) AS collect_conversions,
                           s.last_collected_to, s.backfilled_from, s.entities_synced_at
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
            levels = GRANULARITY_LEVELS.get(acc.get("granularity") or "campaign", ["campaign"])

            if last_to is None or filled_from is None or filled_from > floor:
                start = floor  # 신규 계정 또는 소급 미완료 → 백필 구간 전체
            else:
                start = min(end - timedelta(days=max(days - 1, 0)),
                            last_to - timedelta(days=2))
            start = max(start, floor)
            if start > end:
                continue

            failed = False
            for level in levels:
                for c_start, c_end in _date_chunks(start, end):
                    try:
                        rows = await fetch_performance(
                            client, no, level, c_start, c_end, amn, page_delay=_RATE_DELAY
                        )
                    except Exception as e:  # noqa: BLE001
                        failed = True
                        _log_error(no, f"perf/{level} {c_start}~{c_end}: {e}")
                        await asyncio.sleep(_RATE_DELAY)
                        break
                    facts = [
                        to_fact(r, no, level)
                        for r in rows
                        if r.get("targetDate") and r.get("campaignNo")
                    ]
                    if facts:
                        with account_scoped_connection([no]) as conn:
                            for f in facts:
                                conn.execute(_UPSERT_FACT, f)
                        total += len(facts)
                if failed:
                    break

            # 전환 타입 breakdown(옵션)
            if not failed and acc.get("collect_conversions"):
                for level in levels:
                    for c_start, c_end in _date_chunks(start, end):
                        try:
                            rows = await fetch_conversion(
                                client, no, level, c_start, c_end, amn, page_delay=_RATE_DELAY
                            )
                        except Exception as e:  # noqa: BLE001
                            _log_error(no, f"conv/{level} {c_start}~{c_end}: {e}")
                            await asyncio.sleep(_RATE_DELAY)
                            break
                        cfacts = [
                            to_conversion_fact(r, no, level)
                            for r in rows
                            if r.get("targetDate") and r.get("campaignNo")
                        ]
                        if cfacts:
                            with account_scoped_connection([no]) as conn:
                                for f in cfacts:
                                    conn.execute(_UPSERT_CONV, f)

            if not failed:
                with engine.begin() as conn:
                    conn.execute(_UPSERT_STATE, {"no": no, "start": start, "end": end})

                # 엔티티 이름: 미동기화이거나 TTL 경과 시에만
                synced = acc.get("entities_synced_at")
                stale = synced is None or (
                    (date.today() - synced.date()).days >= _ENTITY_TTL_DAYS
                )
                if stale:
                    await _sync_entities(client, no, amn, levels)

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
        print("\n(운영자: 콘솔에서 키 관리 그룹에 계정을 담으세요)")


if __name__ == "__main__":
    main()
