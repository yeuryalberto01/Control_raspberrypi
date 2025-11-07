"""Utilities to discover and connect to Raspberry Pi devices over SSH."""

from __future__ import annotations

import ipaddress
import logging
import os
import socket
import time
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Union

import paramiko

try:
    from zeroconf import ServiceBrowser, Zeroconf
except ImportError:  # pragma: no cover - optional dependency
    ServiceBrowser = None  # type: ignore
    Zeroconf = None  # type: ignore

DEFAULT_HOSTNAMES: Sequence[str] = ("raspberrypi.local", "raspberrypi")
DEFAULT_SERVICE_TYPES: Sequence[str] = ("_workstation._tcp.local.", "_ssh._tcp.local.")


@dataclass
class DiscoveryResult:
    """Represents a Raspberry Pi candidate discovered via one of the strategies."""

    host: str
    port: int = 22
    source: str = ""
    meta: Dict[str, str] = field(default_factory=dict)


class RaspberryPiDiscoveryError(RuntimeError):
    """Raised when no Raspberry Pi host can be discovered."""


class RaspberryPiDiscoverer:
    """Implements several strategies to locate a Raspberry Pi reachable by SSH."""

    def __init__(
        self,
        user: str = "pi",
        port: int = 22,
        timeout: float = 3.0,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.user = user
        self.port = port
        self.timeout = timeout
        self.log = logger or logging.getLogger(__name__)

    def discover(
        self,
        host: Optional[str] = None,
        hostnames: Optional[Sequence[str]] = None,
        subnet: Optional[str] = None,
        service_types: Optional[Sequence[str]] = None,
        max_scan_hosts: int = 64,
        zeroconf_timeout: float = 4.0,
    ) -> List[DiscoveryResult]:
        """Run all configured discovery strategies and return the unique matches."""

        results: List[DiscoveryResult] = []
        seen: set[str] = set()

        def add(result: Optional[DiscoveryResult]) -> None:
            if not result:
                return
            if result.host in seen:
                return
            seen.add(result.host)
            results.append(result)
            self.log.debug("Discovered Raspberry Pi candidate %s via %s", result.host, result.source)

        primary = (host or os.getenv("PI_HOST") or "").strip()
        if primary:
            add(self._check_host(primary, "env"))

        candidates: List[str] = []
        env_candidates = os.getenv("PI_HOST_CANDIDATES")
        if env_candidates:
            candidates.extend([item.strip() for item in env_candidates.split(",") if item.strip()])
        if hostnames:
            candidates.extend(hostnames)
        else:
            candidates.extend(self._default_hostnames())

        for name in candidates:
            add(self._check_host(name, "hostname"))

        if Zeroconf and ServiceBrowser:
            for result in self._zeroconf(service_types, timeout=zeroconf_timeout):
                add(result)
        else:
            self.log.debug("zeroconf module not available; skipping mDNS discovery.")

        subnet = subnet or os.getenv("PI_SUBNET")
        if subnet:
            for result in self._scan_subnet(subnet, max_hosts=max_scan_hosts):
                add(result)

        return results

    def ensure_host(self, **kwargs: object) -> DiscoveryResult:
        """Ensure at least one candidate exists, raising otherwise."""

        results = self.discover(**kwargs)
        if not results:
            raise RaspberryPiDiscoveryError(
                "No se encontro ninguna Raspberry Pi accesible por SSH."
            )
        return results[0]

    def ssh_client(
        self,
        target: Union[str, DiscoveryResult],
        password: Optional[str] = None,
        key_filename: Optional[str] = None,
        **kwargs: object,
    ) -> paramiko.SSHClient:
        """Create an authenticated Paramiko SSHClient for the resolved host."""

        host = target.host if isinstance(target, DiscoveryResult) else target
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        connect_kwargs = {
            "hostname": host,
            "port": self.port,
            "username": self.user,
            "timeout": self.timeout,
            "password": password,
            "key_filename": key_filename,
        }
        connect_kwargs.update(kwargs)
        filtered = {key: value for key, value in connect_kwargs.items() if value is not None}
        self.log.debug("Opening SSH connection to %s@%s:%s", self.user, host, self.port)
        client.connect(**filtered)
        return client

    def _default_hostnames(self) -> Sequence[str]:
        return DEFAULT_HOSTNAMES

    def _check_host(self, target: str, source: str) -> Optional[DiscoveryResult]:
        try:
            addr = socket.gethostbyname(target)
        except socket.gaierror:
            self.log.debug("No se pudo resolver %s", target)
            return None

        if not self._port_open(addr):
            return None

        meta: Dict[str, str] = {"resolved": addr}
        if target != addr:
            meta["target"] = target
        return DiscoveryResult(host=addr, port=self.port, source=source, meta=meta)

    def _port_open(self, host: str) -> bool:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        try:
            sock.connect((host, self.port))
        except (socket.timeout, OSError):
            return False
        finally:
            sock.close()
        return True

    def _zeroconf(
        self,
        service_types: Optional[Sequence[str]],
        timeout: float,
    ) -> Iterable[DiscoveryResult]:
        if not Zeroconf or not ServiceBrowser:
            return []

        services = list(service_types or DEFAULT_SERVICE_TYPES)
        outer = self

        class Collector:
            def __init__(self) -> None:
                self.items: List[DiscoveryResult] = []

            def add_service(self, zeroconf: Zeroconf, service_type: str, name: str) -> None:
                info = zeroconf.get_service_info(service_type, name, timeout=1000)
                if not info:
                    return
                hostname = info.server.rstrip(".")
                label = f"{hostname} {name}".lower()
                addresses = info.parsed_addresses()
                for addr in addresses:
                    if ":" in addr:  # skip IPv6 addresses until supported
                        continue
                    if "raspberry" not in label and "ssh" not in service_type:
                        continue
                    if not outer._port_open(addr):
                        continue
                    meta = {
                        "service": service_type,
                        "hostname": hostname,
                        "name": name,
                    }
                    self.items.append(
                        DiscoveryResult(host=addr, port=outer.port, source="zeroconf", meta=meta)
                    )

        zeroconf = Zeroconf()
        collector = Collector()
        browsers = [ServiceBrowser(zeroconf, service, collector) for service in services]
        try:
            time.sleep(timeout)
        finally:
            for browser in browsers:
                browser.cancel()
            zeroconf.close()

        return list(collector.items)

    def _scan_subnet(self, subnet: str, max_hosts: int) -> Iterable[DiscoveryResult]:
        try:
            network = ipaddress.ip_network(subnet, strict=False)
        except ValueError:
            self.log.warning("Subnet invalida: %s", subnet)
            return []

        results: List[DiscoveryResult] = []
        checked = 0
        for addr in network.hosts():
            if checked >= max_hosts:
                break
            ip_str = str(addr)
            checked += 1
            if not self._port_open(ip_str):
                continue
            meta = {"subnet": subnet}
            results.append(DiscoveryResult(host=ip_str, port=self.port, source="subnet", meta=meta))
        return results

