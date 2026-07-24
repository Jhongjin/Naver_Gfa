"""운영자 콘솔 API + UI (내부용).

v2: 키를 광고계정 집합에 직접 스코프. 인증은 X-Admin-Token = ADMIN_TOKEN.
경로 /admin 프리픽스, 브로커 앱에 include 되어 단일 함수로 배포.

로컬: uvicorn src.navergfa.admin.app:app --port 8001  →  http://localhost:8001/admin
"""
from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import text

from ..broker.security import generate_api_key
from ..config import settings
from ..db.engine import engine
from .page import HTML_PAGE

router = APIRouter()


def require_admin(x_admin_token: str = Header(default="")) -> None:
    if not settings.admin_token or x_admin_token != settings.admin_token:
        raise HTTPException(status_code=401, detail="unauthorized")


@router.get("/admin", response_class=HTMLResponse)
def page() -> str:
    return HTML_PAGE


@router.get("/admin/api/me")
def me(_: None = Depends(require_admin)) -> dict:
    return {"ok": True}


# ── 키 ──
@router.get("/admin/api/keys")
def list_keys(_: None = Depends(require_admin)) -> dict:
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT k.id, k.label, k.status, k.last_used_at, k.created_at,
                       (SELECT count(*) FROM key_accounts ka WHERE ka.api_key_id = k.id) AS accounts
                  FROM api_keys k
                 ORDER BY k.id DESC
                """
            )
        ).mappings().all()
    return {"data": [dict(r) for r in rows]}


@router.post("/admin/api/keys")
def create_key(body: dict, _: None = Depends(require_admin)) -> dict:
    label = (body.get("label") or "").strip()
    if not label:
        raise HTTPException(400, "label required")
    account_nos = body.get("account_nos") or []
    full, prefix, key_hash = generate_api_key()
    with engine.begin() as conn:
        kid = conn.execute(
            text(
                "INSERT INTO api_keys (label, key_prefix, key_hash) "
                "VALUES (:l, :p, :h) RETURNING id"
            ),
            {"l": label, "p": prefix, "h": key_hash},
        ).scalar()
        for no in account_nos:
            conn.execute(
                text(
                    "INSERT INTO key_accounts (api_key_id, naver_account_no) VALUES (:k, :n) "
                    "ON CONFLICT DO NOTHING"
                ),
                {"k": kid, "n": int(no)},
            )
    return {"id": kid, "api_key": full, "key_prefix": prefix}


@router.get("/admin/api/keys/{key_id}")
def key_detail(key_id: int, _: None = Depends(require_admin)) -> dict:
    with engine.begin() as conn:
        k = conn.execute(
            text(
                "SELECT id, label, status, key_prefix, last_used_at, created_at "
                "FROM api_keys WHERE id = :id"
            ),
            {"id": key_id},
        ).mappings().first()
        if not k:
            raise HTTPException(404, "key not found")
        accts = conn.execute(
            text(
                """
                SELECT ka.naver_account_no, n.account_name, n.manager_account_name
                  FROM key_accounts ka
                  LEFT JOIN naver_accounts n ON n.naver_account_no = ka.naver_account_no
                 WHERE ka.api_key_id = :id
                 ORDER BY ka.naver_account_no
                """
            ),
            {"id": key_id},
        ).mappings().all()
    return {**dict(k), "accounts": [dict(a) for a in accts]}


@router.patch("/admin/api/keys/{key_id}")
def rename_key(key_id: int, body: dict, _: None = Depends(require_admin)) -> dict:
    label = (body.get("label") or "").strip()
    if not label:
        raise HTTPException(400, "label required")
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE api_keys SET label = :l WHERE id = :id"),
            {"l": label, "id": key_id},
        )
    return {"ok": True}


@router.post("/admin/api/keys/{key_id}/accounts")
def add_accounts(key_id: int, body: dict, _: None = Depends(require_admin)) -> dict:
    nos = body.get("account_nos") or []
    if not isinstance(nos, list) or not nos:
        raise HTTPException(400, "account_nos required")
    with engine.begin() as conn:
        for no in nos:
            conn.execute(
                text(
                    "INSERT INTO key_accounts (api_key_id, naver_account_no) VALUES (:k, :n) "
                    "ON CONFLICT DO NOTHING"
                ),
                {"k": key_id, "n": int(no)},
            )
    return {"added": len(nos)}


@router.delete("/admin/api/keys/{key_id}/accounts/{no}")
def remove_account(key_id: int, no: int, _: None = Depends(require_admin)) -> dict:
    with engine.begin() as conn:
        conn.execute(
            text(
                "DELETE FROM key_accounts WHERE api_key_id = :k AND naver_account_no = :n"
            ),
            {"k": key_id, "n": no},
        )
    return {"ok": True}


@router.post("/admin/api/keys/{key_id}/reissue")
def reissue_key(key_id: int, _: None = Depends(require_admin)) -> dict:
    full, prefix, key_hash = generate_api_key()
    with engine.begin() as conn:
        found = conn.execute(
            text(
                "UPDATE api_keys SET key_prefix = :p, key_hash = :h, status = 'active', "
                "revoked_at = NULL WHERE id = :id RETURNING id"
            ),
            {"p": prefix, "h": key_hash, "id": key_id},
        ).scalar()
        if not found:
            raise HTTPException(404, "key not found")
    return {"api_key": full, "key_prefix": prefix}


@router.post("/admin/api/keys/{key_id}/revoke")
def revoke_key(key_id: int, _: None = Depends(require_admin)) -> dict:
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE api_keys SET status='revoked', revoked_at=now() WHERE id=:id"
            ),
            {"id": key_id},
        )
    return {"ok": True}


# ── 광고계정 검색 ──
@router.get("/admin/api/accounts")
def search_accounts(
    q: str = "",
    page: int = 0,
    size: int = 30,
    _: None = Depends(require_admin),
) -> dict:
    params: dict[str, Any] = {"limit": min(size, 100), "offset": page * min(size, 100)}
    where = ""
    if q.strip():
        where = "WHERE (n.account_name ILIKE :q OR CAST(n.naver_account_no AS TEXT) LIKE :q)"
        params["q"] = f"%{q.strip()}%"
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT n.naver_account_no, n.account_name, n.manager_account_name,
                       (SELECT count(*) FROM key_accounts ka WHERE ka.naver_account_no = n.naver_account_no) AS key_count
                  FROM naver_accounts n
                  {where}
                 ORDER BY n.naver_account_no
                 LIMIT :limit OFFSET :offset
                """
            ),
            params,
        ).mappings().all()
    return {"data": [dict(r) for r in rows]}


# ── 사용 현황 (api_audit_logs 집계, 키 기준) ──
@router.get("/admin/api/usage/summary")
def usage_summary(_: None = Depends(require_admin)) -> dict:
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT
                  count(*) FILTER (WHERE ts >= now() - interval '1 day')   AS calls_1d,
                  count(*) FILTER (WHERE ts >= now() - interval '7 days')   AS calls_7d,
                  count(*) FILTER (WHERE ts >= now() - interval '30 days')  AS calls_30d,
                  count(DISTINCT api_key_id) FILTER (WHERE ts >= now() - interval '7 days') AS active_7d,
                  count(*) FILTER (WHERE ts >= now() - interval '7 days' AND status_code >= 400) AS errors_7d
                FROM api_audit_logs
                """
            )
        ).mappings().first()
    return dict(row) if row else {}


@router.get("/admin/api/usage/by-key")
def usage_by_key(days: int = 14, _: None = Depends(require_admin)) -> dict:
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT coalesce(k.label, 'key_'||l.api_key_id::text) AS label,
                       count(*) AS calls, max(l.ts) AS last_call,
                       count(*) FILTER (WHERE l.status_code >= 400) AS errors
                  FROM api_audit_logs l LEFT JOIN api_keys k ON k.id = l.api_key_id
                 WHERE l.ts >= now() - make_interval(days => :d)
                 GROUP BY l.api_key_id, k.label
                 ORDER BY calls DESC LIMIT 100
                """
            ),
            {"d": days},
        ).mappings().all()
    return {"data": [dict(r) for r in rows]}


@router.get("/admin/api/usage/recent")
def usage_recent(limit: int = 40, _: None = Depends(require_admin)) -> dict:
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT l.ts, coalesce(k.label,'key_'||l.api_key_id::text) AS key_label,
                       l.endpoint, l.status_code
                  FROM api_audit_logs l LEFT JOIN api_keys k ON k.id = l.api_key_id
                 ORDER BY l.ts DESC LIMIT :lim
                """
            ),
            {"lim": min(limit, 200)},
        ).mappings().all()
    return {"data": [dict(r) for r in rows]}


@router.get("/admin/api/usage/timeseries")
def usage_timeseries(days: int = 14, _: None = Depends(require_admin)) -> dict:
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT to_char(g.d, 'YYYY-MM-DD') AS d, coalesce(c.calls, 0) AS calls
                  FROM (SELECT ((now() AT TIME ZONE 'Asia/Seoul')::date - offs) AS d
                        FROM generate_series(0, :d - 1) AS offs) g
                  LEFT JOIN (SELECT (ts AT TIME ZONE 'Asia/Seoul')::date AS dd, count(*) AS calls
                             FROM api_audit_logs WHERE ts >= now() - make_interval(days => :d)
                             GROUP BY dd) c ON c.dd = g.d
                 ORDER BY g.d
                """
            ),
            {"d": days},
        ).mappings().all()
    return {"data": [dict(r) for r in rows]}


@router.get("/admin/api/keys/{key_id}/usage")
def key_usage(key_id: int, days: int = 14, _: None = Depends(require_admin)) -> dict:
    with engine.begin() as conn:
        summ = conn.execute(
            text(
                """
                SELECT count(*) FILTER (WHERE ts >= now() - interval '7 days')  AS calls_7d,
                       count(*) FILTER (WHERE ts >= now() - interval '30 days') AS calls_30d,
                       max(ts) AS last_call
                  FROM api_audit_logs WHERE api_key_id = :id
                """
            ),
            {"id": key_id},
        ).mappings().first()
        series = conn.execute(
            text(
                """
                SELECT to_char(g.d, 'YYYY-MM-DD') AS d, coalesce(c.calls, 0) AS calls
                  FROM (SELECT ((now() AT TIME ZONE 'Asia/Seoul')::date - offs) AS d
                        FROM generate_series(0, :d - 1) AS offs) g
                  LEFT JOIN (SELECT (ts AT TIME ZONE 'Asia/Seoul')::date AS dd, count(*) AS calls
                             FROM api_audit_logs
                             WHERE api_key_id = :id AND ts >= now() - make_interval(days => :d)
                             GROUP BY dd) c ON c.dd = g.d
                 ORDER BY g.d
                """
            ),
            {"id": key_id, "d": days},
        ).mappings().all()
    return {"summary": dict(summ) if summ else {}, "series": [dict(r) for r in series]}


# ── 전체 이름 보강 (GitHub Actions 트리거) ──
@router.post("/admin/api/enrich")
def trigger_enrich(_: None = Depends(require_admin)) -> dict:
    if not settings.github_dispatch_token:
        return {
            "triggered": False,
            "message": "GITHUB_DISPATCH_TOKEN 미설정 — GitHub Actions 탭에서 'enrich' 워크플로를 수동 실행하세요.",
        }
    url = f"https://api.github.com/repos/{settings.github_repo}/actions/workflows/enrich.yml/dispatches"
    resp = httpx.post(
        url,
        headers={
            "Authorization": f"Bearer {settings.github_dispatch_token}",
            "Accept": "application/vnd.github+json",
        },
        json={"ref": "main"},
        timeout=20.0,
    )
    if resp.status_code >= 300:
        raise HTTPException(502, f"dispatch 실패: {resp.status_code} {resp.text[:200]}")
    return {"triggered": True, "message": "전체 이름 보강 워크플로를 시작했습니다(수 분 소요)."}


# ── 로컬 단독 실행용 앱 ──
app = FastAPI(title="Naver GFA Admin", version="0.2.0")
app.include_router(router)


@app.get("/")
def _local_root() -> RedirectResponse:
    return RedirectResponse(url="/admin")
