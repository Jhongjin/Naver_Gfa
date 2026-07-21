# 배포 가이드

이 프로젝트는 3개 조각이 서로 다른 곳에 배치된다. **Vercel에는 Broker API만** 올린다.

```
Broker API   → Vercel            (api/index.py, 서버리스)
PostgreSQL   → Neon / Supabase   (관리형 서버리스 Postgres)
Collector    → GitHub Actions cron / 작은 서버  (Vercel 아님)
```

---

## 1. DB — Neon (권장)

1. https://neon.tech 에서 프로젝트 생성 → connection string 복사.
2. Neon은 `postgresql://...` 형식을 준다. **SQLAlchemy용으로 `postgresql+psycopg://` 로 바꾸고**
   서버리스에서는 **pooled(-pooler) 엔드포인트**를 사용한다:
   ```
   DATABASE_URL=postgresql+psycopg://USER:PASS@ep-xxx-pooler.REGION.aws.neon.tech/neondb?sslmode=require
   ```
3. 스키마 적용 (로컬에서 1회):
   ```bash
   psql "postgresql://USER:PASS@ep-xxx.REGION.aws.neon.tech/neondb?sslmode=require" -f db/schema.sql
   ```
   > RLS 격리를 위해 Broker 접속 롤은 BYPASSRLS 없는 제한 롤을 쓰는 것이 이상적이다(운영 단계).

## 2. Broker API — Vercel

- Import: GitHub `Jhongjin/Naver_Gfa`, Branch `main`, Preset **FastAPI**, Root Directory `./`.
- 진입점/라우팅은 리포의 `api/index.py` + `vercel.json` 이 처리한다.
- **Environment Variables** 에 아래를 등록하고 Deploy:
  ```
  DATABASE_URL          = postgresql+psycopg://...-pooler...neon.tech/neondb?sslmode=require
  API_KEY_PEPPER        = <긴 랜덤 문자열>
  NAVER_CLIENT_ID       = <개발자센터>
  NAVER_CLIENT_SECRET   = <개발자센터>
  NAVER_REFRESH_TOKEN   = <tools.get_refresh_token 으로 발급>
  NAVER_MANAGER_ACCOUNT_NO = 4213
  ```
  > NAVER_* 는 Broker 자체에는 당장 필요 없지만(수집은 Collector 담당), 동일 환경을 쓰면 편하다.
- 배포 후 확인: `https://<프로젝트>.vercel.app/health` → `{"status":"ok"}`

## 3. Collector — Vercel 밖 (GitHub Actions cron)

워크플로: [`.github/workflows/collector.yml`](../.github/workflows/collector.yml)
- 매일 05:00 KST 자동 실행 + `Actions` 탭에서 수동 실행(workflow_dispatch) 가능.
- 현재는 **광고계정 트리 동기화**만 수행(리포트 잡은 reports.py 스펙 확정 후 주석 해제).

**필요한 Actions Secrets** (repo Settings > Secrets and variables > Actions > New repository secret):
```
DATABASE_URL          = postgresql+psycopg://...neon.tech/neondb?sslmode=require
NAVER_CLIENT_ID       = <개발자센터>
NAVER_CLIENT_SECRET   = <개발자센터>
NAVER_REFRESH_TOKEN   = <tools.get_refresh_token 으로 발급>
```
(선택) Variables 탭: `NAVER_MANAGER_ACCOUNT_NO` = 4213 (미설정 시 기본 4213)

> 계정 트리 동기화는 호출 1회라 가벼우나, 리포트 수집은 계정 수만큼 반복이라 Actions/서버가 맞다.
> 대안: 작은 상시 서버(VM/컨테이너)에서 APScheduler/cron 으로 주기 실행.

---

## 대안 — 한 곳에 몰기 (컨테이너 호스트)

Broker+Collector+DB를 함께 두려면 Vercel보다 **Railway / Render / Fly.io** 같은 컨테이너 호스트가
자연스럽다. 백그라운드 워커와 상시 프로세스를 그대로 돌릴 수 있어 배치가 단순해진다.
