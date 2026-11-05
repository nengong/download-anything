"""URL boundaries and scoped cookies shared by extraction and transfer code."""
from copy import copy
from http.cookies import SimpleCookie
from urllib.parse import urlsplit

import requests

from core.exceptions import ExtractionError


def is_http_url(url, domains=(), *, https_only=False):
    try:
        if not isinstance(url, str) or any(c.isspace() or ord(c) < 32 for c in url):
            return False
        parsed = urlsplit(url)
        if parsed.scheme not in (("https",) if https_only else ("http", "https")):
            return False
        if not parsed.hostname or parsed.username is not None or parsed.password is not None:
            return False
        if domains and parsed.port not in (None, 443 if parsed.scheme == "https" else 80):
            return False
        # Access .port even for unrestricted HTTP URLs to reject malformed ports.
        parsed.port
        host = parsed.hostname.lower()
        return not domains or any(host == d or host.endswith("." + d) for d in domains)
    except (ValueError, TypeError):
        return False


def require_http_url(url):
    if not is_http_url(url):
        raise ExtractionError("Remote asset must use a valid HTTP(S) URL")
    return url


def scoped_cookies(header, domain):
    """A configured raw header is authorized only for this HTTPS domain."""
    jar = requests.cookies.RequestsCookieJar()
    parsed = SimpleCookie()
    parsed.load(header or "")
    for name, morsel in parsed.items():
        jar.set(name, morsel.value, domain="." + domain, path="/", secure=True)
    return jar


def copy_cookies(source, target):
    for cookie in source or ():
        target.set_cookie(copy(cookie))


def public_headers(headers):
    return {k: v for k, v in (headers or {}).items()
            if k.lower() not in {"cookie", "authorization", "proxy-authorization"}}
