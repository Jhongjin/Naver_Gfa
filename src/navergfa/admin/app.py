"""운영자 콘솔 API + UI (내부용).

인증: 모든 API 는 X-Admin-Token 헤더 = ADMIN_TOKEN 이어야 통과. (광고주 키와 무관한 별도 인증)
경로는 /admin 프리픽스 (Vercel 에서 /admin/* 를 이 함수로 rewrite).

기능: 광고주 등록/조회, 광고계정 검색·배정·해제, API키 발급·폐기, 전체 이름 보강 트리거.

로컬 실행: uvicorn src.navergfa.admin.app:app --port 8001  →  http://localhost:8001/admin
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

# 관리자 라우터 — 브로커 앱에 include 하여 단일 함수로 배포한다(Vercel 멀티함수 회피).
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


# ── 광고주 ──
@router.get("/admin/api/advertisers")
def list_advertisers(_: None = Depends(require_admin)) -> dict:
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT a.id, a.name, a.status,
                       (SELECT count(*) FROM naver_accounts n WHERE n.advertiser_id = a.id) AS accounts,
                       (SELECT count(*) FROM api_keys k WHERE k.advertiser_id = a.id AND k.status='active') AS active_keys
                  FROM advertisers a
                 ORDER BY a.id
                """
            )
        ).mappings().all()
    return {"data": [dict(r) for r in rows]}


@router.post("/admin/api/advertisers")
def create_advertiser(body: dict, _: None = Depends(require_admin)) -> dict:
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name required")
    with engine.begin() as conn:
        existing = conn.execute(
            text("SELECT id FROM advertisers WHERE name = :n"), {"n": name}
        ).scalar()
        if existing:
            return {"id": existing, "created": False}
        new_id = conn.execute(
            text("INSERT INTO advertisers (name) VALUES (:n) RETURNING id"), {"n": name}
        ).scalar()
    return {"id": new_id, "created": True}


# ── 광고계정 검색/배정 ──
@router.get("/admin/api/accounts")
def search_accounts(
    q: str = "",
    assigned: str = "",  # "", "yes", "no"
    page: int = 0,
    size: int = 30,
    _: None = Depends(require_admin),
) -> dict:
    where = []
    params: dict[str, Any] = {"limit": min(size, 100), "offset": page * min(size, 100)}
    if q.strip():
        where.append("(account_name ILIKE :q OR CAST(naver_account_no AS TEXT) LIKE :q)")
        params["q"] = f"%{q.strip()}%"
    if assigned == "yes":
        where.append("advertiser_id IS NOT NULL")
    elif assigned == "no":
        where.append("advertiser_id IS NULL")
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT n.naver_account_no, n.account_name, n.manager_account_name,
                       n.advertiser_id, a.name AS advertiser_name
                  FROM naver_accounts n
                  LEFT JOIN advertisers a ON a.id = n.advertiser_id
                  {clause}
                 ORDER BY n.naver_account_no
                 LIMIT :limit OFFSET :offset
                """
            ),
            params,
        ).mappings().all()
    return {"data": [dict(r) for r in rows]}


@router.post("/admin/api/advertisers/{advertiser_id}/accounts")
def assign_accounts(advertiser_id: int, body: dict, _: None = Depends(require_admin)) -> dict:
    nos = body.get("account_nos") or []
    if not isinstance(nos, list) or not nos:
        raise HTTPException(400, "account_nos required")
    with engine.begin() as conn:
        for no in nos:
            conn.execute(
                text(
                    "UPDATE naver_accounts SET advertiser_id=:aid, updated_at=now() "
                    "WHERE naver_account_no=:no"
                ),
                {"aid": advertiser_id, "no": int(no)},
            )
    return {"assigned": len(nos)}


@router.delete("/admin/api/advertisers/{advertiser_id}/accounts/{no}")
def unassign_account(advertiser_id: int, no: int, _: None = Depends(require_admin)) -> dict:
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE naver_accounts SET advertiser_id=NULL, updated_at=now() "
                "WHERE naver_account_no=:no AND advertiser_id=:aid"
            ),
            {"no": no, "aid": advertiser_id},
        )
    return {"ok": True}


# ── API 키 ──
@router.get("/admin/api/advertisers/{advertiser_id}/keys")
def list_keys(advertiser_id: int, _: None = Depends(require_admin)) -> dict:
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT id, key_prefix, status, last_used_at, created_at "
                "FROM api_keys WHERE advertiser_id=:aid ORDER BY id DESC"
            ),
            {"aid": advertiser_id},
        ).mappings().all()
    return {"data": [dict(r) for r in rows]}


@router.post("/admin/api/advertisers/{advertiser_id}/keys")
def issue_key(advertiser_id: int, _: None = Depends(require_admin)) -> dict:
    full, prefix, key_hash = generate_api_key()
    with engine.begin() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM advertisers WHERE id=:id"), {"id": advertiser_id}
        ).scalar()
        if not exists:
            raise HTTPException(404, "advertiser not found")
        conn.execute(
            text(
                "INSERT INTO api_keys (advertiser_id, key_prefix, key_hash) "
                "VALUES (:aid, :p, :h)"
            ),
            {"aid": advertiser_id, "p": prefix, "h": key_hash},
        )
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


# ── 로컬 단독 실행용 앱 (uvicorn src.navergfa.admin.app:app) ──
app = FastAPI(title="Naver GFA Admin", version="0.1.0")
app.include_router(router)


@app.get("/")
def _local_root() -> RedirectResponse:
    return RedirectResponse(url="/admin")
