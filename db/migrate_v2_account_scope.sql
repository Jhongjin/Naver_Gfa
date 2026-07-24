-- v2 마이그레이션: 키를 "광고계정 집합"에 직접 스코프 (many-to-many)
-- 실행: python -m src.navergfa.tools.init_db --file db/migrate_v2_account_scope.sql

-- 1) api_keys: 라벨 추가, advertiser_id 선택화(레거시 보존)
ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS label TEXT;
ALTER TABLE api_keys ALTER COLUMN advertiser_id DROP NOT NULL;

-- 2) 키 ↔ 광고계정 스코프 (다대다)
CREATE TABLE IF NOT EXISTS key_accounts (
  api_key_id        BIGINT NOT NULL REFERENCES api_keys(id) ON DELETE CASCADE,
  naver_account_no  BIGINT NOT NULL,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (api_key_id, naver_account_no)
);
CREATE INDEX IF NOT EXISTS ix_key_accounts_no ON key_accounts(naver_account_no);

-- 3) 기존 키 스코프 이전(광고주 기준 → 계정 집합) + 라벨 채우기
INSERT INTO key_accounts (api_key_id, naver_account_no)
SELECT k.id, n.naver_account_no
  FROM api_keys k JOIN naver_accounts n ON n.advertiser_id = k.advertiser_id
 WHERE k.advertiser_id IS NOT NULL
ON CONFLICT DO NOTHING;

UPDATE api_keys k SET label = a.name
  FROM advertisers a WHERE a.id = k.advertiser_id AND (k.label IS NULL OR k.label = '');
UPDATE api_keys SET label = 'key_' || id WHERE label IS NULL OR label = '';

-- 4) 광고주 그룹 초기화(접두 오병합 정리) — 계정/이름/성과 데이터는 보존
UPDATE naver_accounts SET advertiser_id = NULL;

-- 5) report_facts: 계정 기준 스코프로 RLS 전환
ALTER TABLE report_facts ALTER COLUMN advertiser_id DROP NOT NULL;
ALTER TABLE report_facts ENABLE ROW LEVEL SECURITY;
ALTER TABLE report_facts FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON report_facts;
DROP POLICY IF EXISTS account_scope ON report_facts;
CREATE POLICY account_scope ON report_facts
  USING (naver_account_no = ANY (
    string_to_array(nullif(current_setting('app.allowed_accounts', true), ''), ',')::bigint[]
  ));
