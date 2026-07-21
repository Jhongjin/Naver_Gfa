"""수집 배치 진입점.

현재 구현: 관리계정 트리에서 광고계정을 발견해 naver_accounts 에 upsert(미할당 상태).
리포트 수집은 네이버 리포트 API 스펙 확정 후 sync_reports() 를 채운다.

실행: python -m src.navergfa.collector.run
"""
from __future__ import annotations

import asyncio

from sqlalchemy import text

from ..config import settings
from ..db.engine import engine
from ..naver.accounts import extract_ad_accounts, fetch_manager_account_tree
from ..naver.client import NaverAdApiClient


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
                """
                INSERT INTO collector_runs (job, started_at, finished_at, rows_upserted, status)
                VALUES ('accounts', now(), now(), :n, 'ok')
                """
            ),
            {"n": len(accounts)},
        )
    return accounts


def main() -> None:
    accounts = asyncio.run(sync_accounts())
    print(f"발견·등록된 광고계정: {len(accounts)}개")
    for a in accounts[:20]:
        print(f"  - {a['naver_account_no']}  {a.get('account_name') or ''}")
    unmapped = "\n(운영자: tools.issue_key 로 광고주에 배정하세요)"
    print(unmapped)


if __name__ == "__main__":
    main()
