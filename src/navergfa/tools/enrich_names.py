"""광고계정 이름 보강 (GET /adAccounts/{no}).

트리 응답엔 계정명이 없어서 번호만 저장된다. 이 도구가 계정 상세를 조회해 account_name 을 채운다.
- 기본: 배정된(advertiser_id 있음) 계정 중 이름이 빈 것만 → 호출 수 최소, 한도 부담 작음.
- --all: 전체 미명 계정(최대 2110개) 보강. 호출이 많으니 한도 회신 후 권장.

실행:
  python -m src.navergfa.tools.enrich_names           # 배정된 계정만
  python -m src.navergfa.tools.enrich_names --all      # 전체
"""
from __future__ import annotations

import argparse
import asyncio
import json

from sqlalchemy import text

from ..config import settings
from ..db.engine import engine
from ..naver.client import NaverAdApiClient

_NAME_KEYS = ("name", "adAccountName", "accountName")


def _pick_name(detail: object) -> str | None:
    if isinstance(detail, dict):
        for k in _NAME_KEYS:
            v = detail.get(k)
            if v:
                return str(v).strip()
    return None


def _targets(all_accounts: bool) -> list[dict]:
    cond = "" if all_accounts else "advertiser_id IS NOT NULL AND"
    with engine.begin() as conn:
        return [
            dict(r)
            for r in conn.execute(
                text(
                    f"""
                    SELECT naver_account_no, manager_account_no
                      FROM naver_accounts
                     WHERE {cond} (account_name IS NULL OR account_name = '')
                     ORDER BY naver_account_no
                    """
                )
            ).mappings()
        ]


async def main(all_accounts: bool, sleep: float) -> None:
    rows = _targets(all_accounts)
    if not rows:
        print("보강 대상 없음.")
        return
    print(f"보강 대상: {len(rows)}개 (all={all_accounts})")

    printed = False
    updated = 0
    total = len(rows)
    async with NaverAdApiClient() as client:
        for i, r in enumerate(rows, 1):
            if i % 100 == 0 or i == total:
                print(f"  ... {i}/{total} 진행 (보강 {updated})")
            no = r["naver_account_no"]
            amn = r.get("manager_account_no") or settings.naver_manager_account_no
            try:
                detail = await client.get(
                    f"/adAccounts/{no}", access_manager_account_no=amn
                )
            except Exception as e:  # noqa: BLE001
                print(f"  {no}: 조회 실패 {e}")
                continue

            if not printed:
                print("\n=== /adAccounts/{no} 응답 샘플(필드 확인용) ===")
                print(json.dumps(detail, ensure_ascii=False, indent=2)[:800])
                print("=== (이름 필드가 다르면 _NAME_KEYS 조정) ===\n")
                printed = True

            name = _pick_name(detail)
            if name:
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            "UPDATE naver_accounts SET account_name=:n, updated_at=now() "
                            "WHERE naver_account_no=:no"
                        ),
                        {"n": name, "no": no},
                    )
                updated += 1
            if sleep:
                await asyncio.sleep(sleep)

    print(f"\n이름 보강 완료: {updated}/{len(rows)}개")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="광고계정 이름 보강")
    p.add_argument("--all", action="store_true", help="배정 안 된 계정까지 전체 보강")
    p.add_argument("--sleep", type=float, default=0.1, help="호출 간 지연(초), 기본 0.1")
    args = p.parse_args()
    asyncio.run(main(args.all, args.sleep))
