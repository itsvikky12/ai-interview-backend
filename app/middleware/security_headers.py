from starlette.types import ASGIApp, Receive, Scope, Send

class SecurityHeadersMiddleware:
    """
    Production-grade Security Headers Middleware.
    Enforces security headers across all API responses (OWASP compliance).
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_security_headers(message: dict):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                
                # Standard Security Headers
                security_headers = [
                    (b"x-frame-options", b"DENY"),
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-xss-protection", b"1; mode=block"),
                    (b"referrer-policy", b"strict-origin-when-cross-origin"),
                    (b"permissions-policy", b"camera=(self), microphone=(self), display-capture=(self)"),
                    (b"strict-transport-security", b"max-age=31536000; includeSubDomains"),
                ]
                
                existing_names = {h[0].lower() for h in headers}
                for name, val in security_headers:
                    if name not in existing_names:
                        headers.append((name, val))
                
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_security_headers)
