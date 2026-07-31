-- v3: 계정별 수집 상태 추적 (백필 · 갭 복구용)
-- 실행: python -m src.navergfa.tools.init_db --file db/migrate_v3_sync_state.sql

CREATE TABLE IF NOT EXISTS account_sync_state (
  naver_account_no   BIGINT PRIMARY KEY,
  backfilled_from    DATE,          -- 이 날짜까지 소급 수집 완료
  last_collected_to  DATE,          -- 마지막으로 수집한 종료일
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 기존에 수집된 계정은 현재 커버리지를 초기 상태로 기록해 둔다
-- (신규 계정만 백필 대상이 되도록. 갭이 있으면 다음 실행에서 자동 복구)
INSERT INTO account_sync_state (naver_account_no, backfilled_from, last_collected_to)
SELECT naver_account_no, min(stat_date), max(stat_date)
  FROM report_facts
 GROUP BY naver_account_no
ON CONFLICT (naver_account_no) DO NOTHING;
