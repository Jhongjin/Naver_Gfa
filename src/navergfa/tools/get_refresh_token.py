"""네이버 로그인 OAuth2 refresh_token 최초 발급 (관리계정 소유자, 1회).

개선판: 리다이렉트되는 code 를 로컬 콜백 서버로 자동 캡처한다(복붙 불필요).
로컬 서버 구동이 안 되면 수동 입력으로 폴백하며, 전체 URL 을 붙여넣어도 code 를 파싱한다.

사전 준비(.env): NAVER_CLIENT_ID, NAVER_CLIENT_SECRET, NAVER_REDIRECT_URI
  (NAVER_REDIRECT_URI 의 host/port 는 개발자센터 Callback URL 과 일치해야 함. 기본 http://localhost:8080/callback)

실행: python -m src.navergfa.tools.get_refresh_token
"""
from __future__ import annotations

import http.server
import secrets
import threading
import urllib.parse
import webbrowser

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


def _capture_via_local_server(host: str, port: int, path: str, timeout: int = 180) -> dict:
    """리다이렉트를 로컬 서버로 받아 code/state 를 캡처. 실패 시 빈 dict."""
    done = threading.Event()
    result: dict = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            if "code" in params:
                result["code"] = params["code"][0]
                result["state"] = params.get("state", [None])[0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(
                    "<h2>인증 완료 ✅ 터미널로 돌아가세요.</h2>".encode("utf-8")
                )
                done.set()
            else:
                self.send_response(200)
                self.end_headers()

        def log_message(self, *args):  # 로그 억제
            pass

    try:
        server = http.server.HTTPServer((host, port), Handler)
    except OSError:
        return {}  # 포트 사용 중 → 폴백
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    ok = done.wait(timeout)
    server.shutdown()
    return result if ok else {}


def _extract_code_state(raw: str) -> tuple[str, str | None]:
    """전체 URL / 'code=..&state=..' / 순수 code 어떤 형태든 code,state 추출."""
    raw = raw.strip()
    if "code=" in raw:
        qs = raw.split("?", 1)[1] if "?" in raw else raw
        params = urllib.parse.parse_qs(qs)
        return params.get("code", [""])[0], params.get("state", [None])[0]
    return raw, None


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

    parsed = urllib.parse.urlparse(settings.naver_redirect_uri)
    host = parsed.hostname or "localhost"
    port = parsed.port or 80
    path = parsed.path or "/callback"

    state = secrets.token_urlsafe(8)
    url = build_authorize_url(state)

    print("\n[1] 브라우저에서 아래 URL 이 열립니다. 4213 권한 계정으로 로그인·동의하세요.")
    print("    (자동으로 안 열리면 아래 URL 을 직접 여세요)\n")
    print("    " + url + "\n")
    try:
        webbrowser.open(url)
    except Exception:
        pass

    print(f"[2] 리다이렉트를 로컬 서버({host}:{port})로 자동 캡처합니다... (최대 3분 대기)")
    captured = _capture_via_local_server(host, port, path)

    if captured.get("code"):
        code = captured["code"]
        returned_state = captured.get("state") or state
        print("    code 자동 캡처 완료 ✅")
    else:
        print("\n[2-폴백] 자동 캡처 실패. 리다이렉트된 주소 전체를 붙여넣으세요")
        print("         (예: http://localhost:8080/callback?code=...&state=...)")
        raw = input("\n    URL 또는 code = ").strip()
        code, parsed_state = _extract_code_state(raw)
        returned_state = parsed_state or state

    if returned_state != state:
        print(f"    ⚠️ state 불일치(요청 {state} / 응답 {returned_state}) — 그래도 시도합니다.")

    data = exchange_code(code, returned_state)
    if "refresh_token" not in data:
        raise SystemExit(f"발급 실패: {data}")

    print("\n[완료] .env 에 아래 한 줄을 저장하세요 (따옴표·공백 없이):\n")
    print(f"NAVER_REFRESH_TOKEN={data['refresh_token']}")
    print(f"\n(access_token 은 자동 갱신됩니다. expires_in={data.get('expires_in')})")


if __name__ == "__main__":
    main()
