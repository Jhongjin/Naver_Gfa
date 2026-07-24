# Naver GFA 광고주 리포팅 API 브로커

렙사가 보유한 네이버 GFA(성과형 디스플레이 광고) 관리계정 자격증명 1개로, **각 광고주가 자사
데이터만** 조회할 수 있는 멀티테넌트 리포팅 플랫폼. 광고주에게 네이버 키는 절대 노출하지 않고,
우리가 발급한 스코프 제한 키로 우리 API만 호출하게 한다.

- 상세 설계: [docs/DESIGN.md](docs/DESIGN.md)
- 파트너 문의(약관/한도): [docs/naver-partner-inquiry.md](docs/naver-partner-inquiry.md)

## 상태 (v2 · 계정 스코프 키)

| 구성 | 상태 |
|---|---|
| 네이버 인증(OAuth2 토큰 매니저) | ✅ 라이브 |
| Collector — 관리계정 트리 수집(2110개) + 이름 보강 | ✅ 라이브 |
| Collector — 성과 수집(활성 키 계정만, 60회/분 스로틀) | ✅ 라이브 |
| DB (Neon PostgreSQL + 계정 기준 RLS) | ✅ 라이브 |
| Broker API — 키 인증·계정 스코프 서빙 | ✅ 라이브 |
| 운영자 콘솔 — 관리(키 그룹) / 사용 현황 / 가이드 | ✅ 라이브 |
| 키 모델 — 광고계정 집합(다대다), 계정 단위/묶음 발급 | ✅ v2 |

> 네이버 공식 답변: 재중계 허용(제3자 위임 이슈는 네이버 미관여 → 책임 렙사), 관리계정 60회/분.
> 실제 광고주 오픈 시 광고주와 데이터 이용 동의 권장.

## 아키텍처 (요약)

```
광고주 --우리 키--> Broker API --RLS--> PostgreSQL <--upsert-- Collector --Bearer--> Naver GFA
                     (읽기전용)                                  (마스터 자격증명은 여기서만)
```

수집 경로(Collector→Naver)와 서빙 경로(광고주→Broker→DB)를 분리한다. 광고주 트래픽이 네이버
쿼터에 영향을 주지 않는다.

## 셋업

```bash
# 1) 가상환경 + 의존성
python -m venv .venv && .venv\Scripts\activate      # Windows
pip install -r requirements.txt

# 2) 환경변수
copy .env.example .env                               # 값 채우기

# 3) 네이버 refresh token 발급 (관리계정 소유자 네이버 로그인, 1회)
python -m src.navergfa.tools.get_refresh_token

# 4) DB 초기화 (PostgreSQL)
psql "%DATABASE_URL%" -f db/schema.sql

# 5) 광고계정 트리 수집
python -m src.navergfa.collector.run

# 6) 브로커 API 기동
uvicorn src.navergfa.broker.app:app --reload

# 7) 광고주 키 발급 (운영자)
python -m src.navergfa.tools.issue_key --advertiser "브랜드몰" --accounts 456,789
```

## 디렉토리

```
db/schema.sql            DDL + Row-Level Security
src/navergfa/
  config.py              설정(.env)
  naver/                 네이버 API 연동 (auth·client·accounts·reports)
  db/engine.py           SQLAlchemy 엔진·세션·테넌트 설정
  collector/run.py       수집 배치 (계정 트리 → upsert)
  broker/                FastAPI 브로커 (app·security)
  tools/                 refresh token 발급 · API 키 발급 CLI
```

## 보안 원칙

- 네이버 마스터 자격증명(Client Secret·refresh token)은 `.env`/시크릿 매니저에만. **커밋 금지.**
- 광고주 요청의 계정번호는 그대로 신뢰하지 않는다 — 키 스코프 ∩ 요청의 교집합만 허용.
- 테넌트 격리는 앱 로직 + PostgreSQL RLS 이중 방어.
- API 키는 해시만 저장(HMAC-SHA256 + 서버 pepper), 발급 시 원문 1회만 노출.
