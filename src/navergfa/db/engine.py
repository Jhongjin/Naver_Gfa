"""SQLAlchemy 엔진 및 테넌트(RLS) 헬퍼."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection

from ..config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)


@contextmanager
def account_scoped_connection(account_nos: Iterator[int]) -> Iterator[Connection]:
    """트랜잭션을 열고 app.allowed_accounts(콤마 구분 계정번호)를 로컬 설정.

    RLS 정책 account_scope 가 이 값으로 report_facts 를 계정 기준 필터링한다.
    조회(브로커)·기록(수집기) 모두 이 컨텍스트로 감싼다. is_local=true.
    """
    joined = ",".join(str(int(n)) for n in account_nos)
    with engine.begin() as conn:
        conn.execute(
            text("SELECT set_config('app.allowed_accounts', :v, true)"),
            {"v": joined},
        )
        yield conn
