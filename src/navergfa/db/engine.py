"""SQLAlchemy 엔진 및 테넌트(RLS) 헬퍼."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection

from ..config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)


@contextmanager
def tenant_connection(advertiser_id: int) -> Iterator[Connection]:
    """트랜잭션을 열고 app.current_tenant 를 로컬 설정한 커넥션을 제공.

    RLS 정책이 이 세션 변수를 기준으로 report_facts 행을 필터링한다.
    is_local=true 이므로 트랜잭션 종료 시 자동 해제된다.
    """
    with engine.begin() as conn:
        conn.execute(
            text("SELECT set_config('app.current_tenant', :tid, true)"),
            {"tid": str(advertiser_id)},
        )
        yield conn
