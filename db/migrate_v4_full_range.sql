-- v4: 전 범위 수집 준비 (캠페인/광고그룹/소재 + 전환 breakdown + 엔티티명)
--     계정별 수집 세밀도 스위치로 비용은 실사용분만 든다.
-- 실행: python -m src.navergfa.tools.init_db --file db/migrate_v4_full_range.sql

-- 1) report_facts: 집계 레벨 구분 + 조회수
ALTER TABLE report_facts ADD COLUMN IF NOT EXISTS level TEXT NOT NULL DEFAULT 'campaign';
ALTER TABLE report_facts ADD COLUMN IF NOT EXISTS views BIGINT NOT NULL DEFAULT 0;
UPDATE report_facts SET ad_group_id = 0 WHERE ad_group_id IS NULL;
ALTER TABLE report_facts ALTER COLUMN ad_group_id SET DEFAULT 0;
ALTER TABLE report_facts ALTER COLUMN ad_group_id SET NOT NULL;

-- PK 를 레벨 포함으로 교체(레벨별 행이 서로 덮어쓰지 않도록)
ALTER TABLE report_facts DROP CONSTRAINT IF EXISTS report_facts_pkey;
ALTER TABLE report_facts
  ADD CONSTRAINT report_facts_pkey
  PRIMARY KEY (naver_account_no, stat_date, level, campaign_id, ad_group_id, ad_id);

-- 2) 계정별 수집 세밀도 스위치
ALTER TABLE naver_accounts ADD COLUMN IF NOT EXISTS granularity TEXT NOT NULL DEFAULT 'campaign';
ALTER TABLE naver_accounts ADD COLUMN IF NOT EXISTS collect_conversions BOOLEAN NOT NULL DEFAULT false;

-- 3) 엔티티(캠페인/광고그룹/소재) 이름 마스터
CREATE TABLE IF NOT EXISTS ad_entities (
  naver_account_no BIGINT NOT NULL,
  level            TEXT   NOT NULL,   -- campaign | adset | creative
  entity_no        BIGINT NOT NULL,
  name             TEXT,
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (naver_account_no, level, entity_no)
);

-- 4) 전환 타입별 breakdown
CREATE TABLE IF NOT EXISTS conversion_facts (
  naver_account_no BIGINT NOT NULL,
  stat_date        DATE   NOT NULL,
  level            TEXT   NOT NULL,
  campaign_id      BIGINT NOT NULL DEFAULT 0,
  ad_group_id      BIGINT NOT NULL DEFAULT 0,
  ad_id            BIGINT NOT NULL DEFAULT 0,
  conv_type        TEXT   NOT NULL,
  conversions      BIGINT NOT NULL DEFAULT 0,
  conv_value       NUMERIC(18,2) NOT NULL DEFAULT 0,
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (naver_account_no, stat_date, level, campaign_id, ad_group_id, ad_id, conv_type)
);

-- 5) 엔티티 동기화 시각(주 1회 갱신용)
ALTER TABLE account_sync_state ADD COLUMN IF NOT EXISTS entities_synced_at TIMESTAMPTZ;

-- 6) RLS: 신규 테이블도 계정 기준 격리
ALTER TABLE ad_entities ENABLE ROW LEVEL SECURITY;
ALTER TABLE ad_entities FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS account_scope ON ad_entities;
CREATE POLICY account_scope ON ad_entities
  USING (naver_account_no = ANY (
    string_to_array(nullif(current_setting('app.allowed_accounts', true), ''), ',')::bigint[]
  ));

ALTER TABLE conversion_facts ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversion_facts FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS account_scope ON conversion_facts;
CREATE POLICY account_scope ON conversion_facts
  USING (naver_account_no = ANY (
    string_to_array(nullif(current_setting('app.allowed_accounts', true), ''), ',')::bigint[]
  ));
