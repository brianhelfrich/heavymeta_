# heavymetal/tests/test_security.py
"""CSP nonce wiring for inline scripts."""

import re


def test_csp_script_src_uses_nonce_not_unsafe_inline(client):
    csp = client.get("/dashboards/").headers["Content-Security-Policy"]
    script_src = csp.split("script-src")[1].split(";")[0]
    assert re.search(r"'nonce-[\w-]+'", script_src), script_src
    assert "'unsafe-inline'" not in script_src


def test_inline_scripts_carry_the_request_nonce(client):
    r = client.get("/dashboards/")
    nonce = re.search(r"'nonce-([\w-]+)'", r.headers["Content-Security-Policy"]).group(
        1
    )
    body = r.get_data(as_text=True)
    inline = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>", body)
    assert inline, "expected inline <script> blocks on the dashboard"
    for tag in inline:
        assert f'nonce="{nonce}"' in tag, f"inline script missing nonce: {tag}"


def test_nonce_is_fresh_per_request(client):
    def grab():
        csp = client.get("/dashboards/").headers["Content-Security-Policy"]
        return re.search(r"'nonce-([\w-]+)'", csp).group(1)

    assert grab() != grab()
