"""DB 스키마 적용 (psql 불필요).

db/schema.sql 을 읽어 DATABASE_URL 로 실행한다.

실행: python -m src.navergfa.tools.init_db
"""
from __future__ import annotations

import pathlib

from sqlalchemy import text

from ..db.engine import engine


def _load_statements() -> list[str]:
    # 리포 루트 기준 db/schema.sql
    root = pathlib.Path(__file__).resolve().parents[3]
    sql = (root / "db" / "schema.sql").read_text(encoding="utf-8")
    # 전체 라인 주석(--) 제거 후 세미콜론으로 분리 (본 스키마엔 문 내부 세미콜론 없음)
    lines = [ln for ln in sql.splitlines() if not ln.strip().startswith("--")]
    body = "\n".join(lines)
    return [s.strip() for s in body.split(";") if s.strip()]


def main() -> None:
    statements = _load_statements()
    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))
    print(f"스키마 적용 완료: {len(statements)}개 문 실행")


if __name__ == "__main__":
    main()
