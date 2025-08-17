from __future__ import annotations

"""Deprecated test routes. Kept as a placeholder to avoid import errors if referenced.

This file intentionally contains no routes. All database test endpoints were removed
in favor of the production-ready schema and APIs.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/testdata", tags=["testdata"])  # no routes
