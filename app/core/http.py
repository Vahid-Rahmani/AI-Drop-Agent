"""Outbound HTTP validation against common SSRF targets."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

import httpx


class OutboundRequestError(ValueError):
    """Raised before an unsafe outbound URL is requested."""


BLOCKED_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",
    "instance-data.ec2.internal",
}


def validate_outbound_url(url: str, allowed_hosts: set[str] | None = None) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise OutboundRequestError("outbound URL must use http or https with a hostname")
    if parsed.username or parsed.password:
        raise OutboundRequestError("outbound URL must not contain credentials")
    hostname = parsed.hostname.lower().rstrip(".")
    if hostname in BLOCKED_HOSTNAMES or hostname.endswith(".local"):
        raise OutboundRequestError("outbound hostname is blocked")
    if allowed_hosts is not None and hostname not in {host.lower() for host in allowed_hosts}:
        raise OutboundRequestError("outbound hostname is not allowlisted")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None and (
        address.is_private or address.is_loopback or address.is_link_local or address.is_reserved
    ):
        raise OutboundRequestError("outbound IP address is not public")
    return url


class SafeHttpClient:
    def __init__(self, allowed_hosts: set[str], timeout: float = 20.0, client=None) -> None:
        self.allowed_hosts = allowed_hosts
        self.client = client or httpx.Client(timeout=timeout, follow_redirects=False)

    def request(self, method: str, url: str, **kwargs):
        validate_outbound_url(url, self.allowed_hosts)
        return self.client.request(method, url, **kwargs)

    def close(self) -> None:
        self.client.close()
