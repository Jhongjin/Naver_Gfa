-- Naver GFA 브로커 스키마 (PostgreSQL) — Phase 1
-- 테넌트 격리는 앱 로직 + Row-Level Security 이중 방어.

-- ── 광고주(테넌트) ──
CREATE TABLE IF NOT EXISTS advertisers (
  id          BIGSERIAL PRIMARY KEY,
  name        TEXT NOT NULL,
  status      TEXT NOT NULL DEFAULT 'active',       -- active | suspended
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── 네이버 광고계정 ↔ 광고주 매핑 = 스코프 원천 ──
-- Collector가 관리계정 트리에서 발견한 계정은 advertiser_id=NULL(미할당)로 먼저 등록되고,
-- 운영자가 광고주에 배정한다.
CREATE TABLE IF NOT EXISTS naver_accounts (
  naver_account_no  BIGINT PRIMARY KEY,
  advertiser_id     BIGINT REFERENCES advertisers(id),   -- NULL = 미할당(발견됨)
  account_name      TEXT,
  discovered_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_naver_accounts_adv ON naver_accounts(advertiser_id);

-- ── 발급 API 키 (해시만 저장) ──
CREATE TABLE IF NOT EXISTS api_keys (
  id             BIGSERIAL PRIMARY KEY,
  advertiser_id  BIGINT NOT NULL REFERENCES advertisers(id),
  key_prefix     TEXT NOT NULL,                    -- 로그/식별용
  key_hash       TEXT NOT NULL,                    -- HMAC-SHA256(pepper, full_key)
  status         TEXT NOT NULL DEFAULT 'active',   -- active | revoked
  last_used_at   TIMESTAMPTZ,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  revoked_at     TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_api_keys_hash ON api_keys(key_hash);
CREATE INDEX IF NOT EXISTS ix_api_keys_adv ON api_keys(advertiser_id);

-- ── 리포트 사실 테이블 (RLS 대상) ──
CREATE TABLE IF NOT EXISTS report_facts (
  advertiser_id     BIGINT NOT NULL REFERENCES advertisers(id),   -- RLS 키
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
CREATE INDEX IF NOT EXISTS ix_report_facts_adv_date ON report_facts(advertiser_id, stat_date);

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

-- ── 수집 실행 관측 ──
CREATE TABLE IF NOT EXISTS collector_runs (
  id                BIGSERIAL PRIMARY KEY,
  job               TEXT,                 -- accounts | reports
  naver_account_no  BIGINT,
  started_at        TIMESTAMPTZ,
  finished_at       TIMESTAMPTZ,
  rows_upserted     BIGINT,
  status            TEXT,                 -- ok | error
  error             TEXT
);

-- ── Row-Level Security ──
-- report_facts: 세션 변수 app.current_tenant 와 일치하는 행만 노출.
-- Broker는 조회 전 SELECT set_config('app.current_tenant', <advertiser_id>, true) 를 호출한다.
ALTER TABLE report_facts ENABLE ROW LEVEL SECURITY;
ALTER TABLE report_facts FORCE ROW LEVEL SECURITY;   -- 소유자도 정책 적용받게 강제
DROP POLICY IF EXISTS tenant_isolation ON report_facts;
CREATE POLICY tenant_isolation ON report_facts
  USING (advertiser_id = NULLIF(current_setting('app.current_tenant', true), '')::BIGINT);

-- 주의: 수집(Collector)은 RLS를 우회해야 하므로 별도 DB 롤(BYPASSRLS) 또는 테이블 소유자로
-- 접속하고, Broker는 BYPASSRLS 없는 제한 롤로 접속하는 것을 권장한다.
