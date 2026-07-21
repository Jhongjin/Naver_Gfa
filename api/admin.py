"""Vercel 서버리스 진입점 — 운영자 콘솔.

vercel.json 이 /admin/* 를 이 함수로 rewrite 한다. ADMIN_TOKEN 으로 보호됨.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.navergfa.admin.app import app  # noqa: E402

__all__ = ["app"]
