"""
api/index.py
============
Vercel Serverless Function entry point for CivicTriage FastAPI backend.
"""

from __future__ import annotations

import os
import sys

# Ensure backend root directory is on sys.path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.main import app

__all__ = ["app"]
