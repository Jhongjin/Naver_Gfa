"""환경설정 (.env 로드)."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

# 사내 보안 프록시가 TLS 를 재서명하는 환경(회사망)에서는 Python 이 OS(Windows) 인증서
# 저장소를 사용하도록 한다. 브라우저가 신뢰하는 사내 루트 CA 를 그대로 활용 → SSL 검증 통과.
# truststore 미설치/미지원 환경에서는 조용히 무시(클라우드는 certifi 로 충분).
try:  # noqa: SIM105
    import truststore

    truststore.inject_into_ssl()
except Exception:
    pass


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # 네이버 로그인 OAuth2 (개발자센터 애플리케이션)
    naver_client_id: str = ""
    naver_client_secret: str = ""
    naver_refresh_token: str = ""
    naver_manager_account_no: int = 4213
    naver_redirect_uri: str = "http://localhost:8080/callback"

    # 네이버 GFA ad-api
    naver_api_base: str = "https://openapi.naver.com/v1/ad-api"
    naver_api_version: int = 1
    naver_token_url: str = "https://nid.naver.com/oauth2.0/token"
    naver_authorize_url: str = "https://nid.naver.com/oauth2.0/authorize"

    # DB
    database_url: str = "postgresql+psycopg://navergfa:navergfa@localhost:5432/navergfa"

    # API 키 해시용 서버 pepper
    api_key_pepper: str = "change-me"

    @property
    def api_prefix(self) -> str:
        return f"{self.naver_api_base}/{self.naver_api_version}"


settings = Settings()
