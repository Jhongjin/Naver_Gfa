# 네이버 GFA 광고주 리포팅 API 브로커 — 상세 설계 (ETL 기준)

> 상태: 초안 v0.1 (2026-07-21) · 방식: ETL 적재 후 서빙 · 1단계 산출물: 광고주용 API 키 발급
> 선행 조건: 네이버 파트너 채널 약관/한도 회신 (docs/naver-partner-inquiry.md 참조)

---

## 1. 목표와 원칙

**목표.** 렙사가 보유한 GFA 관리계정 API 자격증명 1개를 이용해, 각 광고주가 **자사 캠페인 데이터만** API로 가져갈 수 있는 멀티테넌트 리포팅 플랫폼을 구축한다.

**불변 원칙 (절대 위반 금지).**
1. 네이버 마스터 자격증명(관리계정 OAuth 토큰/시크릿)은 **서버 밖으로 절대 나가지 않는다.** 클라이언트·로그·프론트 노출 금지.
2. 광고주는 **우리가 발급한 키**로 **우리 API**만 호출한다. 네이버를 직접 호출하지 않는다.
3. 광고주 요청의 계정 식별자를 **그대로 신뢰하지 않는다.** 항상 `키의 스코프 ∩ 요청 대상`의 교집합만 허용한다.
4. 테넌트 격리는 **앱 로직 + DB Row-Level Security(RLS) 이중 방어**로 구현한다.

---

## 2. 아키텍처 개요

```
  ┌──────────────┐        우리가 발급한 키(scoped)      ┌───────────────────────────┐
  │  광고주 A/B/C │  ──────────────────────────────▶   │      Broker API (읽기 전용) │
  │  자체 대시보드 │  ◀──────  자기 데이터만 JSON  ─────  │  인증→스코프검증→집계 서빙   │
  └──────────────┘                                     └────────────┬──────────────┘
                                                                    │ 읽기 (RLS)
                                                          ┌─────────▼──────────┐
                                                          │   Data Store        │
                                                          │  (PostgreSQL, RLS)  │
                                                          └─────────▲──────────┘
                                                                    │ 쓰기 (upsert)
  ┌──────────────┐   관리계정 OAuth 토큰 (마스터)         ┌──────────┴──────────┐
  │  Naver GFA   │  ◀──────────────────────────────────  │   Collector (배치)   │
  │  Open API    │  ──────────  전 광고계정 리포트  ─────▶ │  스케줄·수집·정규화    │
  └──────────────┘                                        └─────────────────────┘
                                                          Credential Vault ─┘ (마스터 자격증명)
```

**두 개의 독립 경로.**
- **수집 경로 (Collector → Naver):** 마스터 자격증명은 **오직 여기서만** 사용. 통제된 스케줄로만 네이버를 호출 → 공유 쿼터를 지킴.
- **서빙 경로 (광고주 → Broker → DB):** 네이버를 절대 건드리지 않음. 우리 DB에서 RLS로 격리된 데이터만 반환.

이 분리가 핵심이다. 광고주 트래픽이 아무리 몰려도 네이버 쿼터에 영향이 없다.

---

## 3. 데이터 흐름

1. **온보딩.** 운영자가 광고주(tenant)를 등록하고, 그 광고주에게 귀속되는 네이버 광고계정 번호(adAccountNo)들을 매핑한다. 이 매핑이 **스코프의 원천**이다.
2. **수집.** Collector가 스케줄(예: 매시 정각 + 매일 새벽 전일 확정치)에 따라, 매핑된 전 광고계정의 리포트를 관리계정 토큰으로 당겨 `report_facts`에 upsert 한다.
3. **발급.** 운영자가 광고주에게 API 키를 발급한다. 키에는 해당 광고주 tenant_id와 스코프가 박힌다. 원문 키는 발급 순간 1회만 노출, 저장은 해시.
4. **서빙.** 광고주가 키로 Broker API를 호출 → Broker가 키 검증 → tenant_id 확정 → RLS 세션 변수 설정 → DB 조회 → 자기 데이터만 응답.
5. **감사.** 모든 서빙 호출을 `api_audit_logs`에 기록.

---

## 4. 컴포넌트 상세

### 4.1 Credential Vault
- 저장 대상: 관리계정 OAuth `client_id/secret`, `refresh_token`, 현재 `access_token`.
- 저장 위치: 클라우드 Secrets Manager (AWS Secrets Manager / GCP Secret Manager) 또는 Vault. **코드·환경파일 평문 금지.**
- 토큰 갱신: access_token 만료 전 refresh_token으로 자동 재발급하는 리프레셔가 Collector 내부에 상주.

### 4.2 Collector (수집 배치)
- **책임:** 네이버 GFA에서 리포트/구조 데이터를 당겨 정규화 후 DB upsert.
- **Base URL:** `https://openapi.naver.com/v1/ad-api/{version}/...` (version 기본 1), OAuth2 Bearer 인증.
- **계정 열거(확정, 2026-07-21 스펙 확인):**
  - `GET /{v}/managerAccounts/{managerAccountNo}` (헤더 `AccessManagerAccountNo` 필수) 응답이
    **하위 전 depth의 관리계정/광고계정 번호를 계층 구조로 전부 반환** → 광고계정 목록을 이 한 번으로 확보.
  - 보조: `GET /{v}/adAccounts` (page/size 최대 100), `GET /{v}/adAccounts/{adAccountNo}`.
- **스케줄 전략(초안, 한도 회신 후 확정):**
  - 매시 정각: 당일 데이터 갱신 (실시간성 근사)
  - 매일 04:00: 전일·전전일 데이터 확정치 재수집 (네이버 지표 정산 보정)
  - 매일 05:00: 관리계정 상세로 계정 트리 재동기화 (신규 광고계정/캠페인 반영)
- **호출 순서:** `GET /managerAccounts/4213` 로 광고계정 트리 확보 → 각 `adAccountNo`별로 `AccessManagerAccountNo` 헤더 지정하여 리포트 조회.
- **레이트 준수:** 계정 간 호출에 토큰버킷/세마포어를 걸어 **네이버 초당 한도 이하로 스로틀.** 실패는 지수 백오프 재시도.
- **멱등성:** upsert 키 = (naver_account_id, date, campaign_id, ad_id). 재수집해도 중복 안 생김.
- **관측성:** 계정별 마지막 성공 시각·건수·오류를 `collector_runs`에 기록. 지연/실패 알림.

### 4.3 Data Store (PostgreSQL)
- RLS로 테넌트 격리. Broker는 요청마다 `SET app.current_tenant = '<tenant_id>'` 후 조회 → 정책이 자동으로 남의 행을 숨김.
- 사실 테이블은 일자 파티셔닝 권장(조회·보존관리 유리).

### 4.4 Broker API (서빙, 읽기 전용)
- 광고주가 호출하는 유일한 진입점. **쓰기 엔드포인트 없음.**
- 요청 파이프라인: `API키 인증 → tenant 확정 → 요청 파라미터(계정/기간/지표) 검증 → 스코프 교집합 강제 → RLS 세션 → 조회 → 응답 → 감사로그`.
- 응답은 우리 DB 스냅샷 기준이므로 `data_freshness`(마지막 수집 시각)를 함께 내려 신뢰도를 명시.

### 4.5 Key Management & 운영 콘솔
- 발급/회전/폐기, 스코프(허용 광고계정) 지정, 사용량 조회.
- 광고주 self-service 포털은 2단계. 1단계는 운영자 콘솔(내부)로 충분.

---

## 5. 테넌트 격리 (보안 핵심)

**공격 시나리오:** 광고주 A가 자기 키로 `?adAccountNo=<B의 계정>`을 요청.

**방어:**
1. **인증 계층** — 키 해시 조회로 tenant_id(=A) 확정.
2. **스코프 교집합** — A의 키에 허용된 adAccountNo 화이트리스트와 요청 값의 교집합만 통과. 화이트리스트 밖이면 `403`(존재 여부도 흘리지 않도록 A의 계정이 아니면 일괄 403/404 정책 통일).
3. **RLS 최종 방어** — 설령 앱 로직에 버그가 있어도, DB 정책이 `report_facts.tenant_id = current_tenant`가 아닌 행을 물리적으로 반환하지 않음.

**추가 수칙:** 키는 해시(Argon2/bcrypt 또는 HMAC-SHA256+salt)만 저장. 발급 시 prefix(식별용 8자)+secret 구조로 만들어 로그엔 prefix만 남김. 전송은 TLS 강제.

---

## 6. 쿼터 / 레이트리밋

- **네이버 방향(수집):** 마스터 관리계정 단위 공유 한도로 가정. Collector가 유일한 소비자이므로 스로틀+스케줄로 한도 내 유지. → 광고주 수가 늘어도 서빙과 무관.
- **광고주 방향(서빙):** 광고주별 우리 자체 쿼터(예: 분당 N회, 일 M회)를 부과해 공정 분배·남용 방지. `usage_quota`로 카운트.
- **미확정:** 네이버 실제 초당/일일 한도 수치. → 파트너 회신으로 확정 후 Collector 스케줄·병렬도 튜닝.

---

## 7. 데이터 모델 (DDL 초안)

```sql
-- 광고주(테넌트)
CREATE TABLE advertisers (
  id            BIGSERIAL PRIMARY KEY,
  name          TEXT NOT NULL,
  status        TEXT NOT NULL DEFAULT 'active',   -- active | suspended
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 네이버 광고계정 ↔ 광고주 매핑 = 스코프 원천
CREATE TABLE naver_accounts (
  naver_account_no  BIGINT PRIMARY KEY,           -- AccessManagerAccountNo 대상
  advertiser_id     BIGINT NOT NULL REFERENCES advertisers(id),
  account_name      TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 발급 API 키 (해시만 저장)
CREATE TABLE api_keys (
  id             BIGSERIAL PRIMARY KEY,
  advertiser_id  BIGINT NOT NULL REFERENCES advertisers(id),
  key_prefix     TEXT NOT NULL,                   -- 로그/식별용 앞 8자
  key_hash       TEXT NOT NULL,                   -- HMAC-SHA256(secret) 등
  scopes         JSONB NOT NULL DEFAULT '{}',     -- 허용 계정/지표 범위(원천은 naver_accounts, 추가 제한용)
  status         TEXT NOT NULL DEFAULT 'active',  -- active | revoked
  last_used_at   TIMESTAMPTZ,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  revoked_at     TIMESTAMPTZ
);
CREATE UNIQUE INDEX ux_api_keys_hash ON api_keys(key_hash);

-- 리포트 사실 테이블 (RLS 대상, 일자 파티션 권장)
CREATE TABLE report_facts (
  advertiser_id     BIGINT NOT NULL REFERENCES advertisers(id),  -- RLS 키
  naver_account_no  BIGINT NOT NULL,
  stat_date         DATE   NOT NULL,
  campaign_id       BIGINT NOT NULL,
  ad_group_id       BIGINT,
  ad_id             BIGINT,
  impressions       BIGINT NOT NULL DEFAULT 0,
  clicks            BIGINT NOT NULL DEFAULT 0,
  cost              NUMERIC(18,2) NOT NULL DEFAULT 0,
  conversions       BIGINT NOT NULL DEFAULT 0,
  conv_value        NUMERIC(18,2) NOT NULL DEFAULT 0,
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (naver_account_no, stat_date, campaign_id, ad_id)
);

-- 감사 로그
CREATE TABLE api_audit_logs (
  id            BIGSERIAL PRIMARY KEY,
  api_key_id    BIGINT REFERENCES api_keys(id),
  advertiser_id BIGINT,
  endpoint      TEXT,
  params        JSONB,
  status_code   INT,
  ip            INET,
  ts            TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 광고주별 서빙 쿼터
CREATE TABLE usage_quota (
  advertiser_id BIGINT NOT NULL REFERENCES advertisers(id),
  window_start  TIMESTAMPTZ NOT NULL,
  count         INT NOT NULL DEFAULT 0,
  PRIMARY KEY (advertiser_id, window_start)
);

-- 수집 실행 관측
CREATE TABLE collector_runs (
  id                BIGSERIAL PRIMARY KEY,
  naver_account_no  BIGINT,
  started_at        TIMESTAMPTZ,
  finished_at       TIMESTAMPTZ,
  rows_upserted     BIGINT,
  status            TEXT,          -- ok | error
  error             TEXT
);

-- ── RLS 설정 ──
ALTER TABLE report_facts ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON report_facts
  USING (advertiser_id = current_setting('app.current_tenant')::BIGINT);
-- Broker DB 롤은 BYPASSRLS 없이 사용. 수집용 롤만 별도로 정책 우회 권한 부여.
```

---

## 8. Broker API 스펙 (초안)

인증: `Authorization: Bearer <발급키>` 헤더. 모든 응답은 `data_freshness` 포함.

### GET /v1/accounts
내 광고계정 목록(스코프 내).
```json
{ "data": [ { "naver_account_no": 456, "account_name": "브랜드몰" } ],
  "data_freshness": "2026-07-21T09:00:00+09:00" }
```

### GET /v1/reports
캠페인/일자별 리포트.
- 쿼리: `account_no`(선택, 미지정 시 스코프 전체), `date_from`, `date_to`, `group_by=campaign|ad_group|ad|date`, `metrics=impressions,clicks,cost,conversions`
- 스코프 밖 `account_no` 지정 시 `403`.
```json
{ "data": [
    { "stat_date":"2026-07-20","campaign_id":111,"impressions":10520,
      "clicks":210,"cost":315000,"conversions":18 }
  ],
  "paging": { "next": null },
  "data_freshness": "2026-07-21T09:00:00+09:00" }
```

### GET /v1/reports/summary
기간 합계/파생지표(CTR·CPC·CPA·ROAS).

**공통 에러:** `401`(키 무효), `403`(스코프 위반), `429`(쿼터 초과), `503`(수집 지연으로 데이터 미확정).

---

## 9. 기술 스택 (제안)

| 영역 | 선택 | 이유 |
|---|---|---|
| 언어/프레임워크 | Python **FastAPI** 또는 Node **NestJS** | 배치+프록시 균형, 타입·검증 강함 |
| DB | **PostgreSQL** | RLS 네이티브 → 테넌트 격리 최적 |
| 캐시/쿼터 | **Redis** | 서빙 레이트리밋 카운터 |
| 스케줄러 | cron / **APScheduler** / Temporal | 수집 배치 |
| 시크릿 | Cloud Secrets Manager | 마스터 자격증명 보관 |
| 배포 | 컨테이너(단일 서비스로 시작, Collector/Broker 프로세스 분리) | 운영 단순 |

> Collector와 Broker는 **DB만 공유하고 프로세스는 분리**한다. 수집 장애가 서빙을 죽이지 않게.

---

## 10. 로드맵

- **Phase 0 (선행/차단):** 네이버 파트너 약관·한도 회신 확보 → 방식·스케줄 확정.
- **Phase 1 — Collector + DB:** 마스터 토큰으로 전 계정 리포트를 `report_facts`에 적재. 멱등 upsert·스로틀·관측. **← 심장, 여기부터 착수 가능.**
- **Phase 2 — Broker API + 키/스코핑:** 인증·RLS·스코프 교집합·감사. 침투 테스트(A로 B 조회 시도)로 격리 검증.
- **Phase 3 — 운영 콘솔:** 광고주 온보딩, 계정 매핑, 키 관리, 사용량.
- **Phase 4 — 광고주 대시보드 UI (상품화, 2단계).**
- **Phase 5 — 쿼터/과금/모니터링/알림 고도화.**

---

## 11. 열린 이슈 (네이버 회신 대기)

1. 재중계 형태의 약관 허용 여부 — **차단 이슈.**
2. 관리계정 quota 수치 → Collector 병렬도/스케줄 확정.
3. 리포트 API의 지원 지표·집계 단위·소급 기간(백필 범위).
4. 계정/캠페인 구조 변경 웹훅 유무(없으면 폴링 동기화).

## 12. 광고주센터 실물 확인 (2026-07-21, 스크린샷)

`ads.naver.com > 도구 > 디스플레이 광고 API 관리` (Beta) 화면에서 확인:
- 관리계정: **4213 = 나스미디어_대표관리계정** (계정 책임자).
- **API 사용 = "애플리케이션" 등록 모델.** 각 애플리케이션이 자격증명 단위로 추정. 현재 활성 2개:
  `미디어채널2팀_테스트`(2026.07.07 등록), `성과형 DA CBT`(2023.04.12 등록).
- 지원 메뉴: **API 가이드 / 기술 문의(문의접수) / 이용 약관** 버튼 존재.
  - **이용 약관** → 재중계 허용 여부 확인 경로 (약관 원문 확인 필요).
  - **기술 문의(문의접수)** → quota 등 파트너 문의 접수 창구. (naver-partner-inquiry.md 내용을 여기로)
- **판단:** 애플리케이션을 광고주별로 등록해도 전부 관리계정 4213에 귀속 → 하위 전 광고계정 접근 가능성이 높아 **네이버 단 격리는 기대 불가, 브로커 계층 필수**(본 설계 유지).
  단, 애플리케이션 상세에 "접근 가능 광고계정 지정" 옵션이 있으면 격리 일부 위임 가능 → 재검토 대상.
- 미확인: quota 수치.
- **확정(2026-07-21, API 스펙 확인):** 애플리케이션/자격증명 단위 광고계정 스코프 지정 개념 **없음.**
  접근권한은 관리계정 멤버십/role 기반 → 관리계정 4213 자격증명은 하위 전 광고계정 접근.
  **네이버 단 격리 불가 → 브로커 스코핑이 유일 격리 수단.** (본 설계 확정)

## 13. 이용약관 분석 (2026-07-21, 약관 원문 시행일 2023-04-25)

**종합 판단:** 브로커 설계는 약관이 예정한 "대행사 클라이언트" 모델에 부합. 단 제9조 9항(제3자 제공 금지) 해석 때문에 **출시 전 네이버 서면 확인 필수**(유일 차단 리스크).

**뒷받침 조항(초록불):**
- 제2조 4호: API 서비스는 "회원 또는 회원이 권한을 위임한 **광고 대행사**가 구축한 웹/앱에서 광고 정보 이용"하도록 하는 것 → 대행사 클라이언트 구축이 정상 사용.
- 제5조 2항·제7조 5항: 액세스 라이선스/비밀키 제3자 전달 금지 → 우리가 네이버 키를 광고주에 주면 안 되는 근거. 브로커 필수.
- 제7조 4항·제9조 4항: API 데이터는 "사용자 본인 및 권한 기능으로 권한 가진 다른 회원의 광고 관리 목적" 범위 내 사용 가능 → 위임받은 광고주에게 본인 데이터만 제공은 이 범위.

**회색지대(차단 리스크):** 제9조 9항·제7조 6항 "제3자 제공/공개 금지". 광고주가 "제3자"냐 "권한 가진 다른 회원"이냐 해석 문제. 엄격 스코핑(A는 A만) 지키면 후자로 볼 여지 크고, 9항 문구가 "입찰 등 정보"라 경쟁정보 유출 방지 취지로 읽히나, self-service API 연동·유상과금 허용 여부는 서면 확인 필요.

**약관 강제 설계 제약(반영 필수):**
- 제7조 4항: 광고주 권한 상실 시 해당 데이터 **즉시 삭제** → 오프보딩 삭제 기능 구현.
- 제7조 3항·제17조 2항: API 데이터 **시각적 구분 표시 + 네이버 소유 명시** → 대시보드 출처 라벨/저작권 표기.
- 제7조 6항: API 외 자동수집(스크래핑) 금지 → Collector 공식 API만.
- 제10조 6항: 회사가 rate limit 부과·비공개 재조정 → ETL 정당화, quota 문의 확인.
- 제14조: API 무상 → 광고주 과금 시 제3자 제공 논란 확대, 문의 시 함께 확인.
- 제9조 5·6항: 128bit SSL 이상 + 보안점검 협조 → TLS 강제.
- 제17조: API 데이터 IP는 네이버 귀속.
