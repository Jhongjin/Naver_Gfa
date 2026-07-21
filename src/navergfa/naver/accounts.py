"""광고계정/관리계정 조회.

핵심: GET /managerAccounts/{no} (헤더 AccessManagerAccountNo 필수) 응답은
하위 전 depth 의 관리계정/광고계정 번호를 계층 구조로 포함한다 → 이 한 번으로
관리계정 하위의 모든 광고계정을 열거한다.
"""
from __future__ import annotations

from typing import Any

from .client import NaverAdApiClient


async def fetch_manager_account_tree(
    client: NaverAdApiClient, manager_account_no: int
) -> Any:
    """관리계정 상세 = 하위 계정 트리."""
    return await client.get(
        f"/managerAccounts/{manager_account_no}",
        access_manager_account_no=manager_account_no,
    )


# 응답 스키마의 정확한 필드명은 실데이터로 확정 필요(광고계정 번호/계정명 키).
# 후보 키를 방어적으로 탐색한다. 실제 응답 확인 후 아래 상수만 조정하면 된다.
_ACCOUNT_NO_KEYS = ("adAccountNo", "adAccountId", "accountNo", "accountId", "no")
_ACCOUNT_NAME_KEYS = ("adAccountName", "accountName", "name")
_AD_ACCOUNT_MARKERS = ("adAccount",)  # 이 키가 광고계정 노드/목록을 담는다고 가정


def extract_ad_accounts(tree: Any) -> list[dict[str, Any]]:
    """트리 응답에서 (naver_account_no, account_name) 목록을 추출.

    관리계정 노드와 광고계정 노드가 섞인 계층 구조를 가정하고, '광고계정'으로 보이는
    노드만 수집한다. TODO: 실제 응답 스키마 확인 후 정확한 경로 기반 파싱으로 교체.
    """
    found: dict[int, str | None] = {}

    def looks_like_ad_account(node: dict[str, Any]) -> bool:
        # 관리계정(managerAccount) 노드가 아니고, 계정번호 키를 가진 노드
        if any("manager" in k.lower() for k in node):
            # 광고계정 목록을 별도 키로 품고 있을 수 있으므로 자식 탐색은 계속
            pass
        return any(k in node for k in _ACCOUNT_NO_KEYS)

    def pick(node: dict[str, Any], keys: tuple[str, ...]) -> Any:
        for k in keys:
            if k in node and node[k] is not None:
                return node[k]
        return None

    def walk(obj: Any, under_ad_marker: bool) -> None:
        if isinstance(obj, dict):
            is_ad_ctx = under_ad_marker or any(
                m.lower() in k.lower() for k in obj for m in _AD_ACCOUNT_MARKERS
            )
            no = pick(obj, _ACCOUNT_NO_KEYS)
            if no is not None and is_ad_ctx:
                try:
                    found[int(no)] = pick(obj, _ACCOUNT_NAME_KEYS)
                except (TypeError, ValueError):
                    pass
            for k, v in obj.items():
                child_marker = under_ad_marker or any(
                    m.lower() in k.lower() for m in _AD_ACCOUNT_MARKERS
                )
                walk(v, child_marker)
        elif isinstance(obj, list):
            for item in obj:
                walk(item, under_ad_marker)

    walk(tree, False)
    return [{"naver_account_no": no, "account_name": name} for no, name in found.items()]
