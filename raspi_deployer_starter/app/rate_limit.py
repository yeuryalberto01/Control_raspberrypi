"""
Very simple per-minute rate limiter middleware.
"""

from __future__ import annotations

import time
from typing import Dict, Tuple

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware


class SimpleRateLimit(BaseHTTPMiddleware):
    def __init__(self, app, limit_per_min: int = 300):
        super().__init__(app)
        self.limit = limit_per_min
        self.bucket: Dict[Tuple[str, int], int] = {}

    async def dispatch(self, request: Request, call_next):
        client = request.client.host if request.client else "anonymous"
        minute_window = int(time.time() // 60)
        key = (client, minute_window)
        self.bucket[key] = self.bucket.get(key, 0) + 1
        if self.bucket[key] > self.limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too Many Requests",
            )
        return await call_next(request)
