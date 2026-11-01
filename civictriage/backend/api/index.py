"""
api/index.py
============
Vercel Serverless Function entry point for CivicTriage FastAPI backend.
Vercel automatically detects this file when the backend root is deployed.
"""

from __future__ import annotations

import os
import sys

# Ensure backend root directory is on sys.path so 'app' imports work seamlessly
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.main import app

# Vercel's Python runtime exposes 'app' as the ASGI application
__all__ = ["app"]

