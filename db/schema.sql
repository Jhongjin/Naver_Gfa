-- Naver GFA 브로커 스키마 (PostgreSQL) — v2: 계정 스코프 키
-- 키는 광고계정 집합(key_accounts)에 직접 스코프된다. RLS는 계정 기준.

-- ── 광고주(선택적 라벨/그룹 — v2에서는 필수 아님) ──
CREATE TABLE IF NOT EXISTS advertisers (
  id          BIGSERIAL PRIMARY KEY,
  name        TEXT NOT NULL,
  status      TEXT NOT NULL DEFAULT 'active',
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── 네이버 광고계정 (수집기가 발견·보강) ──
CREATE TABLE IF NOT EXISTS naver_accounts (
  naver_account_no      BIGINT PRIMARY KEY,
  advertiser_id         BIGINT REFERENCES advertisers(id),   -- 선택적 그룹(레거시)
  account_name          TEXT,
  manager_account_no    BIGINT,
  manager_account_name  TEXT,
  discovered_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_naver_accounts_name ON naver_accounts(account_name);

-- ── API 키 (해시만 저장) ──
CREATE TABLE IF NOT EXISTS api_keys (
  id             BIGSERIAL PRIMARY KEY,
  label          TEXT,                             -- 키 이름(광고주/브랜드 등 가독용)
  advertiser_id  BIGINT REFERENCES advertisers(id),-- 레거시(선택)
  key_prefix     TEXT NOT NULL,
  key_hash       TEXT NOT NULL,
  status         TEXT NOT NULL DEFAULT 'active',    -- active | revoked
  last_used_at   TIMESTAMPTZ,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  revoked_at     TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_api_keys_hash ON api_keys(key_hash);

-- ── 키 ↔ 광고계정 스코프 (다대다) ──
CREATE TABLE IF NOT EXISTS key_accounts (
  api_key_id        BIGINT NOT NULL REFERENCES api_keys(id) ON DELETE CASCADE,
  naver_account_no  BIGINT NOT NULL,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (api_key_id, naver_account_no)
);
CREATE INDEX IF NOT EXISTS ix_key_accounts_no ON key_accounts(naver_account_no);

-- ── 리포트 사실 테이블 (RLS: 계정 기준) ──
CREATE TABLE IF NOT EXISTS report_facts (
  advertiser_id     BIGINT,                        -- 레거시(선택)
  naver_account_no  BIGINT NOT NULL,
  stat_date         DATE   NOT NULL,
  campaign_id       BIGINT NOT NULL,
  ad_group_id       BIGINT,
  ad_id             BIGINT NOT NULL DEFAULT 0,
  impressions       BIGINT NOT NULL DEFAULT 0,
  clicks            BIGINT NOT NULL DEFAULT 0,
  cost              NUMERIC(18,2) NOT NULL DEFAULT 0,
  conversions       BIGINT NOT NULL DEFAULT 0,
  conv_value        NUMERIC(18,2) NOT NULL DEFAULT 0,
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (naver_account_no, stat_date, campaign_id, ad_id)
);
CREATE INDEX IF NOT EXISTS ix_report_facts_acct_date ON report_facts(naver_account_no, stat_date);

-- ── 감사 로그 ──
CREATE TABLE IF NOT EXISTS api_audit_logs (
  id            BIGSERIAL PRIMARY KEY,
  api_key_id    BIGINT,
  advertiser_id BIGINT,
  endpoint      TEXT,
  params        JSONB,
  status_code   INT,
  ip            INET,
  ts            TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_audit_key_ts ON api_audit_logs(api_key_id, ts);

-- ── 수집 실행 관측 ──
CREATE TABLE IF NOT EXISTS collector_runs (
  id                BIGSERIAL PRIMARY KEY,
  job               TEXT,
  naver_account_no  BIGINT,
  started_at        TIMESTAMPTZ,
  finished_at       TIMESTAMPTZ,
  rows_upserted     BIGINT,
  status            TEXT,
  error             TEXT
);

-- ── Row-Level Security: 계정 기준 ──
-- 브로커/수집기는 조회·기록 전 app.allowed_accounts(콤마 구분 계정번호)를 설정한다.
ALTER TABLE report_facts ENABLE ROW LEVEL SECURITY;
ALTER TABLE report_facts FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON report_facts;
DROP POLICY IF EXISTS account_scope ON report_facts;
CREATE POLICY account_scope ON report_facts
  USING (naver_account_no = ANY (
    string_to_array(nullif(current_setting('app.allowed_accounts', true), ''), ',')::bigint[]
  ));
