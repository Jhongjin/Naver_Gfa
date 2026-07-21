"""연결 진단 (DB 불필요, 읽기 전용).

발급한 refresh_token → access_token → ad-api 관리계정 트리 조회까지 검증하고,
응답 구조(필드명)와 추출된 광고계정 수를 출력한다. DB 는 건드리지 않는다.

실행: python -m src.navergfa.tools.probe
"""
from __future__ import annotations

import asyncio
import json

from ..config import settings
from ..naver.accounts import extract_ad_accounts, fetch_manager_account_tree
from ..naver.client import NaverAdApiClient


def _find_first_account_node(obj, depth=0):
    """계정번호 후보 키를 가진 첫 dict 노드를 찾아 반환(구조 확인용)."""
    keys = ("adAccountNo", "adAccountId", "accountNo", "accountId", "no")
    if isinstance(obj, dict):
        if any(k in obj for k in keys):
            return obj
        for v in obj.values():
            r = _find_first_account_node(v, depth + 1)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for item in obj:
            r = _find_first_account_node(item, depth + 1)
            if r is not None:
                return r
    return None


async def main() -> None:
    print("1) access_token 발급 시도...")
    async with NaverAdApiClient() as client:
        print("2) GET /managerAccounts/{} 조회...".format(settings.naver_manager_account_no))
        tree = await fetch_manager_account_tree(client, settings.naver_manager_account_no)

    print("\n=== 응답 최상위 구조 ===")
    if isinstance(tree, dict):
        print("top-level keys:", list(tree.keys()))
    else:
        print("type:", type(tree).__name__)

    sample = _find_first_account_node(tree)
    print("\n=== 광고계정 노드 샘플(필드명 확인용) ===")
    print(json.dumps(sample, ensure_ascii=False, indent=2)[:1500] if sample else "계정 노드 미발견")

    accounts = extract_ad_accounts(tree)
    print(f"\n=== extract_ad_accounts 결과: {len(accounts)}개 ===")
    for a in accounts[:10]:
        print(f"  - {a['naver_account_no']}  {a.get('account_name') or ''}")
    print("\n(위 샘플/개수를 공유해 주시면 파싱을 확정합니다. 민감하면 계정명은 가려도 됩니다.)")


if __name__ == "__main__":
    asyncio.run(main())
