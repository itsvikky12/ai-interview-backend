from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.responses import JSONResponse
from app.utils.redis_client import get_redis, RedisCache
from app.config import get_settings

settings = get_settings()

# Global limit: 5x the per-path limit, per IP across all endpoints
GLOBAL_RATE_LIMIT = settings.RATE_LIMIT_PER_MINUTE * 5


class RateLimitMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "")
        path = scope.get("path", "")

        if (
            settings.DEBUG
            or method == "OPTIONS"
            or path.startswith("/docs")
            or path.startswith("/openapi")
        ):
            await self.app(scope, receive, send)
            return

        # Get client IP
        client = scope.get("client")
        client_ip = client[0] if client else "unknown"

        try:
            redis_client = await get_redis()
            cache = RedisCache(redis_client)

            # Global per-IP limit
            global_key = f"rate_limit:global:{client_ip}"
            global_count = await cache.incr(global_key, ttl=60)
            if global_count > GLOBAL_RATE_LIMIT:
                response = JSONResponse(
                    status_code=429,
                    content={"detail": "Global rate limit exceeded. Try again later."},
                )
                await response(scope, receive, send)
                return

            # Per-path limit
            path_key = f"rate_limit:{client_ip}:{path}"
            path_count = await cache.incr(path_key, ttl=60)
            if path_count > settings.RATE_LIMIT_PER_MINUTE:
                response = JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded. Try again later."},
                )
                await response(scope, receive, send)
                return
        except Exception:
            pass  # If Redis is down, don't block requests

        await self.app(scope, receive, send)
