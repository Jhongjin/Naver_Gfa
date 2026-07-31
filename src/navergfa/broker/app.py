"""브로커 FastAPI 앱 (읽기 전용).

v2: 키는 광고계정 집합(key_accounts)에 직접 스코프된다.
파이프라인: 키 인증 → 키의 허용 계정 로드 → 요청 계정이 스코프 내인지 확인 →
계정 기준 RLS 조회 → 감사로그.

기동: uvicorn src.navergfa.broker.app:app --reload
"""
from __future__ import annotations

import json
from datetime import date
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from sqlalchemy import text

from ..admin.app import router as admin_router
from ..db.engine import account_scoped_connection, engine
from .security import hash_api_key

app = FastAPI(title="Naver GFA Broker API", version="0.2.0")
# 운영자 콘솔(/admin, /admin/api/*) 을 같은 함수에 포함 (ADMIN_TOKEN 별도 인증)
app.include_router(admin_router)


def authenticate(authorization: str = Header(...)) -> dict[str, Any]:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="invalid authorization header")
    token = authorization.split(" ", 1)[1].strip()
    key_hash = hash_api_key(token)
    with engine.begin() as conn:
        row = (
            conn.execute(
                text("SELECT id, status FROM api_keys WHERE key_hash = :h"),
                {"h": key_hash},
            )
            .mappings()
            .first()
        )
        if not row or row["status"] != "active":
            raise HTTPException(status_code=401, detail="invalid api key")
        accounts = list(
            conn.execute(
                text(
                    "SELECT naver_account_no FROM key_accounts WHERE api_key_id = :id"
                ),
                {"id": row["id"]},
            ).scalars()
        )
        conn.execute(
            text("UPDATE api_keys SET last_used_at = now() WHERE id = :id"),
            {"id": row["id"]},
        )
    return {"api_key_id": row["id"], "accounts": accounts}


def _audit(auth: dict, request: Request, status_code: int, params: dict) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO api_audit_logs (api_key_id, endpoint, params, status_code, ip) "
                "VALUES (:kid, :ep, :params, :sc, :ip)"
            ),
            {
                "kid": auth["api_key_id"],
                "ep": request.url.path,
                "params": json.dumps(params, default=str),
                "sc": status_code,
                "ip": request.client.host if request.client else None,
            },
        )


def _coverage(targets: list[int]) -> dict[str, Any]:
    """요청 스코프의 실제 데이터 커버리지.

    data_through   : 데이터가 존재하는 최신 일자(= 어디까지 조회 가능한지)
    last_synced_at : 마지막 수집 반영 시각
    data_freshness : last_synced_at 과 동일(하위호환용 별칭)
    """
    if not targets:
        return {"data_through": None, "last_synced_at": None, "data_freshness": None}
    with account_scoped_connection(targets) as conn:
        row = (
            conn.execute(
                text(
                    "SELECT max(stat_date) AS through, max(updated_at) AS synced "
                    "FROM report_facts WHERE naver_account_no = ANY(:t)"
                ),
                {"t": targets},
            )
            .mappings()
            .first()
        )
    through = row["through"].isoformat() if row and row["through"] else None
    synced = row["synced"].isoformat() if row and row["synced"] else None
    return {"data_through": through, "last_synced_at": synced, "data_freshness": synced}


@app.get("/")
def root() -> dict[str, Any]:
    return {
        "service": "naver-gfa broker",
        "endpoints": ["/health", "/v1/accounts", "/v1/reports"],
        "admin": "/admin",
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/accounts")
def list_accounts(request: Request, auth: dict = Depends(authenticate)) -> dict[str, Any]:
    scope = auth["accounts"]
    if not scope:
        _audit(auth, request, 200, {})
        return {"data": [], **_coverage([])}
    # 계정별 data_through 를 함께 제공(그 계정에 데이터가 어디까지 있는지)
    with account_scoped_connection(scope) as conn:
        rows = (
            conn.execute(
                text(
                    """
                    SELECT n.naver_account_no, n.account_name,
                           (SELECT max(f.stat_date) FROM report_facts f
                             WHERE f.naver_account_no = n.naver_account_no) AS data_through
                      FROM naver_accounts n
                     WHERE n.naver_account_no = ANY(:scope)
                     ORDER BY n.naver_account_no
                    """
                ),
                {"scope": scope},
            )
            .mappings()
            .all()
        )
    _audit(auth, request, 200, {})
    return {"data": [dict(r) for r in rows], **_coverage(scope)}


@app.get("/v1/reports")
def get_reports(
    request: Request,
    date_from: date = Query(...),
    date_to: date = Query(...),
    account_no: int | None = Query(None, description="미지정 시 스코프 전체"),
    auth: dict = Depends(authenticate),
) -> dict[str, Any]:
    scope = set(auth["accounts"])
    if not scope:
        raise HTTPException(status_code=403, detail="key has no accounts in scope")

    if account_no is not None:
        if account_no not in scope:
            _audit(auth, request, 403, {"account_no": account_no})
            raise HTTPException(status_code=403, detail="account not in key scope")
        targets = [account_no]
    else:
        targets = sorted(scope)

    # 계정 기준 RLS(app.allowed_accounts) + 명시 필터 이중 방어
    with account_scoped_connection(targets) as conn:
        rows = (
            conn.execute(
                text(
                    """
                    SELECT stat_date, naver_account_no, campaign_id,
                           sum(impressions) AS impressions,
                           sum(clicks)      AS clicks,
                           sum(cost)        AS cost,
                           sum(conversions) AS conversions,
                           sum(conv_value)  AS conv_value
                      FROM report_facts
                     WHERE naver_account_no = ANY(:targets)
                       AND stat_date BETWEEN :d1 AND :d2
                  GROUP BY stat_date, naver_account_no, campaign_id
                  ORDER BY stat_date, naver_account_no, campaign_id
                    """
                ),
                {"targets": targets, "d1": date_from, "d2": date_to},
            )
            .mappings()
            .all()
        )
    _audit(auth, request, 200, {"account_no": account_no, "from": date_from, "to": date_to})
    return {"data": [dict(r) for r in rows], **_coverage(targets)}


# ── 임시 진단(라우팅 확인용). 원인 확정 후 제거 예정 ──
# 모든 라우트 정의 뒤에 위치해야 실제 라우트를 가리지 않는다.
@app.get("/{_diag_path:path}")
def _diag(_diag_path: str, request: Request) -> dict[str, Any]:
    return {
        "_diag": "route-not-matched",
        "path": request.scope.get("path"),
        "raw_path": str(request.scope.get("raw_path")),
        "root_path": request.scope.get("root_path"),
        "registered": sorted(
            {getattr(r, "path", "") for r in app.routes if getattr(r, "path", "")}
        ),
    }
