"""Vercel 서버리스 진입점.

Vercel의 Python 런타임이 이 파일에서 ASGI 앱(app)을 찾아 서빙한다.
vercel.json 의 rewrite 가 모든 경로를 이 함수로 보낸다.

주의: Collector(백그라운드 배치)와 PostgreSQL 은 Vercel 이 아닌 별도 호스트에서 운영한다.
이 진입점은 광고주용 Broker API(읽기 전용)만 노출한다.
"""
import os
import sys

# 리포 루트를 import 경로에 추가 (src 레이아웃)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.navergfa.broker.app import app  # noqa: E402

__all__ = ["app"]
