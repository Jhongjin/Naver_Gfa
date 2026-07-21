"""네이버 로그인 OAuth2 refresh_token 최초 발급 (관리계정 소유자, 1회).

절차:
  1) 개발자센터(https://developers.naver.com)에 애플리케이션 등록 → Client ID/Secret,
     Callback URL(= NAVER_REDIRECT_URI)을 .env 에 설정.
  2) 이 스크립트를 실행 → 출력된 authorize URL 을 관리계정 소유자가 브라우저에서 열고 로그인·동의.
  3) 리다이렉트된 주소의 `code`(및 `state`) 값을 콘솔에 붙여넣기.
  4) 출력된 refresh_token 을 .env 의 NAVER_REFRESH_TOKEN 에 저장.

실행: python -m src.navergfa.tools.get_refresh_token
"""
from __future__ import annotations

import secrets
import urllib.parse

import httpx

from ..config import settings


def build_authorize_url(state: str) -> str:
    q = {
        "response_type": "code",
        "client_id": settings.naver_client_id,
        "redirect_uri": settings.naver_redirect_uri,
        "state": state,
    }
    return f"{settings.naver_authorize_url}?{urllib.parse.urlencode(q)}"


def exchange_code(code: str, state: str) -> dict:
    resp = httpx.post(
        settings.naver_token_url,
        params={
            "grant_type": "authorization_code",
            "client_id": settings.naver_client_id,
            "client_secret": settings.naver_client_secret,
            "code": code,
            "state": state,
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()


def main() -> None:
    if not settings.naver_client_id or not settings.naver_client_secret:
        raise SystemExit("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 를 .env 에 먼저 설정하세요.")

    state = secrets.token_urlsafe(8)
    print("\n[1] 아래 URL 을 관리계정 소유자 브라우저에서 열어 로그인·동의하세요:\n")
    print("    " + build_authorize_url(state))
    print(
        "\n[2] 리다이렉트된 주소(...&code=XXXX&state=YYYY)에서 code 값을 붙여넣으세요."
    )
    code = input("\n    code = ").strip()
    returned_state = input(f"    state = (기본 {state}) ").strip() or state

    data = exchange_code(code, returned_state)
    if "refresh_token" not in data:
        raise SystemExit(f"발급 실패: {data}")

    print("\n[완료] .env 에 아래를 저장하세요:\n")
    print(f"NAVER_REFRESH_TOKEN={data['refresh_token']}")
    print(f"\n(access_token 은 자동 갱신됩니다. expires_in={data.get('expires_in')})")


if __name__ == "__main__":
    main()
