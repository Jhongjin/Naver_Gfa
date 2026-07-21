"""브로커 FastAPI 앱 (읽기 전용).

파이프라인: API키 인증 → 광고주(tenant) 확정 → 스코프 교집합 강제 → RLS 세션 조회 → 감사로그.
광고주는 우리가 발급한 키로 우리 API만 호출한다. 네이버는 절대 직접 호출하지 않는다.

기동: uvicorn src.navergfa.broker.app:app --reload
"""
from __future__ import annotations

import json
from datetime import date
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from sqlalchemy import text

from ..db.engine import engine, tenant_connection
from .security import hash_api_key

app = FastAPI(title="Naver GFA Broker API", version="0.1.0")


def authenticate(authorization: str = Header(...)) -> dict[str, Any]:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="invalid authorization header")
    token = authorization.split(" ", 1)[1].strip()
    key_hash = hash_api_key(token)
    with engine.begin() as conn:
        row = (
            conn.execute(
                text(
                    """
                    SELECT id, advertiser_id, status
                      FROM api_keys
                     WHERE key_hash = :h
                    """
                ),
                {"h": key_hash},
            )
            .mappings()
            .first()
        )
        if not row or row["status"] != "active":
            raise HTTPException(status_code=401, detail="invalid api key")
        conn.execute(
            text("UPDATE api_keys SET last_used_at = now() WHERE id = :id"),
            {"id": row["id"]},
        )
    return {"api_key_id": row["id"], "advertiser_id": row["advertiser_id"]}


def _audit(auth: dict, request: Request, status_code: int, params: dict) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO api_audit_logs
                       (api_key_id, advertiser_id, endpoint, params, status_code, ip)
                VALUES (:kid, :aid, :ep, :params, :sc, :ip)
                """
            ),
            {
                "kid": auth["api_key_id"],
                "aid": auth["advertiser_id"],
                "ep": request.url.path,
                "params": json.dumps(params, default=str),
                "sc": status_code,
                "ip": request.client.host if request.client else None,
            },
        )


def _scoped_account_nos(advertiser_id: int) -> set[int]:
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT naver_account_no FROM naver_accounts WHERE advertiser_id = :aid"
            ),
            {"aid": advertiser_id},
        ).scalars()
        return set(rows)


def _freshness() -> str | None:
    with engine.begin() as conn:
        val = conn.execute(
            text("SELECT max(updated_at) FROM report_facts")
        ).scalar()
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
    with tenant_connection(auth["advertiser_id"]) as conn:
        rows = (
            conn.execute(
                text(
                    """
                    SELECT naver_account_no, account_name
                      FROM naver_accounts
                     WHERE advertiser_id = :aid
                     ORDER BY naver_account_no
                    """
                ),
                {"aid": auth["advertiser_id"]},
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
    scope = _scoped_account_nos(auth["advertiser_id"])
    if not scope:
        raise HTTPException(status_code=403, detail="no accounts in scope")

    # 스코프 교집합 강제: 요청한 계정이 내 스코프 밖이면 거부
    if account_no is not None:
        if account_no not in scope:
            _audit(auth, request, 403, {"account_no": account_no})
            raise HTTPException(status_code=403, detail="account not in scope")
        targets = [account_no]
    else:
        targets = sorted(scope)

    # RLS(app.current_tenant) + 명시적 advertiser_id 필터 이중 방어
    with tenant_connection(auth["advertiser_id"]) as conn:
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
                     WHERE advertiser_id = :aid
                       AND naver_account_no = ANY(:targets)
                       AND stat_date BETWEEN :d1 AND :d2
                  GROUP BY stat_date, naver_account_no, campaign_id
                  ORDER BY stat_date, naver_account_no, campaign_id
                    """
                ),
                {
                    "aid": auth["advertiser_id"],
                    "targets": targets,
                    "d1": date_from,
                    "d2": date_to,
                },
            )
            .mappings()
            .all()
        )
    _audit(auth, request, 200, {"account_no": account_no, "from": date_from, "to": date_to})
    return {"data": [dict(r) for r in rows], "data_freshness": _freshness()}
