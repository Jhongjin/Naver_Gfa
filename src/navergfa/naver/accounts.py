"""광고계정/관리계정 조회.

관리계정 상세 응답 구조(2026-07-21 실데이터 확정):
  {
    "no": 4213, "name": "...", "disabled": false,
    "childManagerAccounts": [ {같은 구조, 재귀}, ... ],
    "childAdAccountNos": [230, 1212, ...]      # 광고계정은 '번호'로만 들어있음
  }

즉 광고계정은 객체가 아니라 각 관리계정 노드의 childAdAccountNos(정수 리스트)에 담긴다.
계정명은 이 응답에 없으므로, 필요 시 GET /adAccounts/{no} 로 별도 조회한다.
"""
from __future__ import annotations

from typing import Any

from .client import NaverAdApiClient


async def fetch_manager_account_tree(
    client: NaverAdApiClient, manager_account_no: int
) -> Any:
    """관리계정 상세 = 하위 전 depth 관리계정/광고계정 트리."""
    return await client.get(
        f"/managerAccounts/{manager_account_no}",
        access_manager_account_no=manager_account_no,
    )


def extract_ad_accounts(tree: dict[str, Any]) -> list[dict[str, Any]]:
    """트리에서 모든 광고계정 번호를 수집.

    childManagerAccounts 를 재귀 순회하며 각 노드의 childAdAccountNos 를 모은다.
    각 광고계정에 대해 직속 관리계정(팀) 정보를 함께 기록한다. 계정명은 별도 조회 필요(None).
    반환: [{naver_account_no, account_name(None), manager_account_no, manager_account_name}]
    """
    result: dict[int, dict[str, Any]] = {}

    def walk(node: dict[str, Any]) -> None:
        manager_no = node.get("no")
        manager_name = (node.get("name") or "").strip() or None
        for ad_no in node.get("childAdAccountNos") or []:
            try:
                n = int(ad_no)
            except (TypeError, ValueError):
                continue
            # 첫 등장(가장 가까운 관리계정) 기준으로 기록
            result.setdefault(
                n,
                {
                    "naver_account_no": n,
                    "account_name": None,
                    "manager_account_no": manager_no,
                    "manager_account_name": manager_name,
                },
            )
        for child in node.get("childManagerAccounts") or []:
            walk(child)

    if isinstance(tree, dict):
        walk(tree)
    return list(result.values())


def extract_manager_accounts(tree: dict[str, Any]) -> list[dict[str, Any]]:
    """트리에서 관리계정(팀) 목록을 수집."""
    result: dict[int, dict[str, Any]] = {}

    def walk(node: dict[str, Any]) -> None:
        no = node.get("no")
        if isinstance(no, int):
            result.setdefault(
                no,
                {"manager_account_no": no, "name": (node.get("name") or "").strip() or None},
            )
        for child in node.get("childManagerAccounts") or []:
            walk(child)

    if isinstance(tree, dict):
        walk(tree)
    return list(result.values())
