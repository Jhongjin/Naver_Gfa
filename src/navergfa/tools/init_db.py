"""DB 스키마/마이그레이션 적용 (psql 불필요).

기본은 db/schema.sql, --file 로 다른 SQL 파일 지정 가능.

실행:
  python -m src.navergfa.tools.init_db
  python -m src.navergfa.tools.init_db --file db/migrate_v2_account_scope.sql
"""
from __future__ import annotations

import argparse
import pathlib

from sqlalchemy import text

from ..db.engine import engine


def _load_statements(rel: str = "db/schema.sql") -> list[str]:
    root = pathlib.Path(__file__).resolve().parents[3]
    sql = (root / rel).read_text(encoding="utf-8")
    # 전체 라인 주석(--) 제거 후 세미콜론으로 분리 (본 스키마엔 문 내부 세미콜론 없음)
    lines = [ln for ln in sql.splitlines() if not ln.strip().startswith("--")]
    body = "\n".join(lines)
    return [s.strip() for s in body.split(";") if s.strip()]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--file", default="db/schema.sql", help="적용할 SQL 파일(리포 루트 기준)")
    args = p.parse_args()
    statements = _load_statements(args.file)
    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))
    print(f"적용 완료: {args.file} — {len(statements)}개 문 실행")


if __name__ == "__main__":
    main()
