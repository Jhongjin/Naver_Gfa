"""광고주 등록 + 광고계정 배정 + API 키 발급 (운영자용).

- 광고주(advertisers)를 생성(또는 이름으로 재사용)한다.
- 지정한 네이버 광고계정들을 그 광고주에 배정(naver_accounts.advertiser_id)한다.
  (계정은 먼저 collector.run 으로 발견되어 있어야 한다. 없으면 새로 등록한다.)
- API 키를 발급하고 원문을 1회만 출력한다. (해시만 저장)

실행 예:
  python -m src.navergfa.tools.issue_key --advertiser "브랜드몰" --accounts 456,789
"""
from __future__ import annotations

import argparse

from sqlalchemy import text

from ..broker.security import generate_api_key
from ..db.engine import engine


def issue(advertiser_name: str, account_nos: list[int]) -> None:
    full_key, prefix, key_hash = generate_api_key()

    with engine.begin() as conn:
        advertiser_id = conn.execute(
            text("SELECT id FROM advertisers WHERE name = :n"),
            {"n": advertiser_name},
        ).scalar()
        if advertiser_id is None:
            advertiser_id = conn.execute(
                text(
                    "INSERT INTO advertisers (name) VALUES (:n) RETURNING id"
                ),
                {"n": advertiser_name},
            ).scalar()

        for no in account_nos:
            conn.execute(
                text(
                    """
                    INSERT INTO naver_accounts (naver_account_no, advertiser_id, updated_at)
                    VALUES (:no, :aid, now())
                    ON CONFLICT (naver_account_no) DO UPDATE
                       SET advertiser_id = :aid, updated_at = now()
                    """
                ),
                {"no": no, "aid": advertiser_id},
            )

        conn.execute(
            text(
                """
                INSERT INTO api_keys (advertiser_id, key_prefix, key_hash)
                VALUES (:aid, :prefix, :hash)
                """
            ),
            {"aid": advertiser_id, "prefix": prefix, "hash": key_hash},
        )

    print(f"\n광고주: {advertiser_name} (id={advertiser_id})")
    print(f"배정 광고계정: {account_nos}")
    print("\n⚠️  아래 API 키는 지금 한 번만 표시됩니다. 광고주에게 안전하게 전달하세요:\n")
    print(f"    {full_key}\n")


def main() -> None:
    p = argparse.ArgumentParser(description="광고주 API 키 발급")
    p.add_argument("--advertiser", required=True, help="광고주명")
    p.add_argument(
        "--accounts",
        required=True,
        help="배정할 네이버 광고계정 번호 (콤마 구분). 예: 456,789",
    )
    args = p.parse_args()
    account_nos = [int(x) for x in args.accounts.split(",") if x.strip()]
    issue(args.advertiser, account_nos)


if __name__ == "__main__":
    main()
