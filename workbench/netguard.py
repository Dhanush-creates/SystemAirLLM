"""Egress guard: every model endpoint must resolve to this machine (or the LAN if allowed)."""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


class EgressBlocked(RuntimeError):
    pass


def check_local(url: str, allow_private: bool = False) -> None:
    host = urlparse(url).hostname
    if not host:
        raise EgressBlocked(f"no host in URL: {url}")
    try:
        addrs = {info[4][0] for info in socket.getaddrinfo(host, None)}
    except OSError as e:
        raise EgressBlocked(f"cannot resolve {host}: {e}") from e
    for addr in addrs:
        ip = ipaddress.ip_address(addr.split("%")[0])
        if not (ip.is_loopback or (allow_private and ip.is_private)):
            raise EgressBlocked(f"blocked non-local endpoint {host} ({ip})")
