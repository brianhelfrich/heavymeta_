# heavymetal/backend/security.py
"""Global HTTP security headers — single source of truth.

Applied to every response and wired up by the app factory via
register_security_headers(app). Keep header policy here, not inline in create_app.
"""

import secrets

from flask import Flask, g


def register_security_headers(app: Flask) -> None:
    @app.before_request
    def _set_csp_nonce() -> None:
        # Fresh per request; used in the CSP header and on each inline <script>.
        g.csp_nonce = secrets.token_urlsafe(16)

    @app.context_processor
    def _inject_csp_nonce() -> dict:
        return {"csp_nonce": g.get("csp_nonce", "")}

    @app.after_request
    def set_security_headers(resp):
        # Enforce HTTPS for 6 months (includeSubDomains if you own them)
        resp.headers.setdefault(
            "Strict-Transport-Security", "max-age=15552000; includeSubDomains; preload"
        )
        # Prevent MIME sniffing
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        # Clickjacking protection (redundant if CSP frame-ancestors is set)
        resp.headers.setdefault("X-Frame-Options", "DENY")
        # Limit referrer leakage
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        # Permissions Policy — disable sensitive APIs you don't use
        resp.headers.setdefault(
            "Permissions-Policy",
            "geolocation=(), microphone=(), camera=(), payment=(), usb=()",
        )
        # COOP to isolate browsing context (safe default)
        resp.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")

        # Content Security Policy. Inline <script> blocks carry a per-request
        # nonce (no 'unsafe-inline' for scripts). style-src keeps 'unsafe-inline'
        # because inline style="…" attributes are pervasive and nonces don't
        # cover attributes — only <style>/<script> elements.
        nonce = g.get("csp_nonce", "")
        csp = (
            "default-src 'self'; "
            "base-uri 'self'; "
            "object-src 'none'; "
            "img-src 'self' data:; "
            "font-src 'self' data:; "
            "style-src 'self' 'unsafe-inline'; "
            f"script-src 'self' 'nonce-{nonce}'; "
            "connect-src 'self'; "
            "frame-ancestors 'none'"
        )
        resp.headers.setdefault("Content-Security-Policy", csp)
        return resp
