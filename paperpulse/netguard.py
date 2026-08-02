"""Shared no-redirect HTTP opener for outbound fetches to allowlisted hosts.

A URL that passes a host allowlist can still be an SSRF vector if the request
is allowed to follow a redirect: the allowlisted host issues a 3xx to an
internal/metadata address (169.254.169.254, 127.0.0.1, ...) and the default
opener follows it with no re-validation against the allowlist. Every outbound
fetch that first checks a host allowlist must route through this opener, not
urllib's default one, or the allowlist check is decorative.
"""

from __future__ import annotations

import urllib.request


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


NO_REDIRECT_OPENER = urllib.request.build_opener(_NoRedirect)

__all__ = ["NO_REDIRECT_OPENER"]
