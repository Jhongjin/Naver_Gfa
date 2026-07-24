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


def _freshness() -> str | None:
    with engine.begin() as conn:
        val = conn.execute(text("SELECT max(updated_at) FROM report_facts")).scalar()
        return val.isoformat() if val else None


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
        return {"data": [], "data_freshness": _freshness()}
    with engine.begin() as conn:
        rows = (
            conn.execute(
                text(
                    "SELECT naver_account_no, account_name FROM naver_accounts "
                    "WHERE naver_account_no = ANY(:scope) ORDER BY naver_account_no"
                ),
                {"scope": scope},
            )
            .mappings()
            .all()
        )
    _audit(auth, request, 200, {})
    return {"data": [dict(r) for r in rows], "data_freshness": _freshness()}


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
                           sum(conversions) AS conversions
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
    return {"data": [dict(r) for r in rows], "data_freshness": _freshness()}
