"""광고계정 → 광고주 자동 생성·배정.

GFA 광고계정명이 곧 브랜드/광고주인 점을 이용해, 이름이 채워진 광고계정으로부터
광고주를 자동 생성하고 계정을 배정한다. (Naver 호출 없음, DB 작업만)

전제: 계정명이 채워져 있어야 함 → 먼저 enrich_names --all 로 이름 보강 필요.

모드:
  기본(1:1)       : 계정명 그대로 광고주 생성, 그 계정 1개 배정.
  --group-prefix  : 계정명 접두(첫 '_' 또는 공백 앞)로 묶어 한 광고주에 여러 계정 배정.
                    예) '엠에스헬스케어_신비감플러스','엠에스헬스케어_리프팅' → '엠에스헬스케어'

옵션:
  --include-assigned : 이미 배정된 계정도 대상(기본은 미배정만).
  --apply            : 실제 적용(미지정 시 미리보기만).

실행 예:
  python -m src.navergfa.tools.auto_provision --group-prefix            # 미리보기
  python -m src.navergfa.tools.auto_provision --group-prefix --apply    # 적용
"""
from __future__ import annotations

import argparse
import re

from sqlalchemy import text

from ..db.engine import engine

_SEP = re.compile(r"[ _]")


def _advertiser_name(account_name: str, group_prefix: bool) -> str:
    name = account_name.strip()
    if group_prefix:
        parts = _SEP.split(name, maxsplit=1)
        return parts[0].strip() or name
    return name


def main(group_prefix: bool, include_assigned: bool, apply: bool) -> None:
    cond = "account_name IS NOT NULL AND account_name <> ''"
    if not include_assigned:
        cond += " AND advertiser_id IS NULL"

    with engine.begin() as conn:
        rows = [
            dict(r)
            for r in conn.execute(
                text(f"SELECT naver_account_no, account_name FROM naver_accounts WHERE {cond}")
            ).mappings()
        ]

    if not rows:
        print("대상 계정 없음. (이름 보강 먼저: enrich_names --all)")
        return

    # 광고주명 → 계정번호들
    groups: dict[str, list[int]] = {}
    for r in rows:
        adv = _advertiser_name(r["account_name"], group_prefix)
        groups.setdefault(adv, []).append(r["naver_account_no"])

    print(f"대상 계정 {len(rows)}개 → 광고주 {len(groups)}개 (group_prefix={group_prefix})")
    for adv, nos in list(groups.items())[:20]:
        print(f"  - {adv}  ({len(nos)}개 계정)")
    if len(groups) > 20:
        print(f"  ... 외 {len(groups)-20}개")

    if not apply:
        print("\n[미리보기] 실제 적용하려면 --apply 를 붙이세요.")
        return

    created = 0
    assigned = 0
    with engine.begin() as conn:
        for adv, nos in groups.items():
            aid = conn.execute(
                text("SELECT id FROM advertisers WHERE name = :n"), {"n": adv}
            ).scalar()
            if aid is None:
                aid = conn.execute(
                    text("INSERT INTO advertisers (name) VALUES (:n) RETURNING id"),
                    {"n": adv},
                ).scalar()
                created += 1
            for no in nos:
                conn.execute(
                    text(
                        "UPDATE naver_accounts SET advertiser_id=:aid, updated_at=now() "
                        "WHERE naver_account_no=:no"
                    ),
                    {"aid": aid, "no": no},
                )
                assigned += 1

    print(f"\n적용 완료: 광고주 {created}개 신규 생성, 계정 {assigned}개 배정.")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="계정명 기반 광고주 자동 생성·배정")
    p.add_argument("--group-prefix", action="store_true", help="계정명 접두로 묶기")
    p.add_argument("--include-assigned", action="store_true", help="배정된 계정도 대상")
    p.add_argument("--apply", action="store_true", help="실제 적용(미지정 시 미리보기)")
    args = p.parse_args()
    main(args.group_prefix, args.include_assigned, args.apply)
