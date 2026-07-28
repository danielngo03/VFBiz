"""Credential-free HTTPS source reader with SSRF and size controls."""

from __future__ import annotations

import ipaddress
import socket
import tempfile
from types import TracebackType
from typing import BinaryIO
from urllib.parse import urljoin, urlparse, urlunparse

import httpx

from app.modules.datasets.application.source_intake.models import ApprovedSourceFetchPlan
from app.modules.datasets.domain import RegistryInvariantError


class TemporaryOpenedSource:
    def __init__(self, stream: BinaryIO, byte_size: int) -> None:
        self.stream = stream
        self.byte_size = byte_size

    def __enter__(self) -> TemporaryOpenedSource:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.stream.close()


class ControlledHttpSourceReader:
    _PRIVATE_NETWORKS = (
        ipaddress.ip_network("0.0.0.0/8"),
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("100.64.0.0/10"),
        ipaddress.ip_network("127.0.0.0/8"),
        ipaddress.ip_network("169.254.0.0/16"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("224.0.0.0/4"),
        ipaddress.ip_network("::/128"),
        ipaddress.ip_network("::1/128"),
        ipaddress.ip_network("fc00::/7"),
        ipaddress.ip_network("fe80::/10"),
    )

    def __init__(self, *, client: httpx.Client) -> None:
        self._client = client

    def open(self, plan: ApprovedSourceFetchPlan) -> TemporaryOpenedSource:
        initial_host = _https_host(plan.url)
        allowed_hosts = {initial_host, *plan.allowed_redirect_hosts}

        current_url = plan.url
        response = self._send_pinned(current_url)
        temporary = tempfile.TemporaryFile()
        try:
            redirects = 0
            while response.is_redirect:
                redirects += 1
                if redirects > 3:
                    raise RegistryInvariantError("dataset fetch exceeds redirect limit")
                location = response.headers.get("location")
                if not location:
                    raise RegistryInvariantError("dataset redirect is missing a location")
                target = urljoin(current_url, location)
                host = _https_host(target)
                if host not in allowed_hosts:
                    raise RegistryInvariantError("dataset redirect host is not allowlisted")
                response.close()
                current_url = target
                response = self._send_pinned(current_url)
            response.raise_for_status()
            size = 0
            for chunk in response.iter_bytes(1024 * 1024):
                size += len(chunk)
                if size > plan.max_bytes:
                    raise RegistryInvariantError(
                        "downloaded artifact exceeds configured byte limit"
                    )
                temporary.write(chunk)
            temporary.seek(0)
            return TemporaryOpenedSource(temporary, size)
        except BaseException:
            temporary.close()
            raise
        finally:
            response.close()

    def _send_pinned(self, logical_url: str) -> httpx.Response:
        parsed = urlparse(logical_url)
        host = _https_host(logical_url)
        addresses = self._resolve_public_addresses(host)
        pinned_host = addresses[0]
        if ":" in pinned_host:
            pinned_host = f"[{pinned_host}]"
        port = parsed.port
        pinned_netloc = pinned_host if port in (None, 443) else f"{pinned_host}:{port}"
        pinned_url = urlunparse(parsed._replace(netloc=pinned_netloc))
        host_header = host if port in (None, 443) else f"{host}:{port}"
        request = self._client.build_request(
            "GET",
            pinned_url,
            headers={"host": host_header},
        )
        request.extensions["sni_hostname"] = host
        return self._client.send(request, stream=True)

    def _resolve_public_addresses(self, host: str) -> tuple[str, ...]:
        addresses = {
            ipaddress.ip_address(item[4][0])
            for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        }
        if not addresses or any(
            not address.is_global
            or any(address in network for network in self._PRIVATE_NETWORKS)
            for address in addresses
        ):
            raise RegistryInvariantError("dataset origin resolves to a non-public address")
        return tuple(sorted(str(address) for address in addresses))


def _https_host(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise RegistryInvariantError("dataset URL must be credential-free HTTPS")
    return parsed.hostname
