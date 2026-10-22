"""Phase 1 NAT-PMP adapter. PCP and UPnP are deliberately non-mutating.

The packet helpers are pure so fake-gateway tests never contact a real router.
"""

from __future__ import annotations

import socket
import struct
from dataclasses import dataclass, replace

from .policy import Mapping


class BackendError(RuntimeError):
    """Router outcome may be uncertain; the caller must retain its intent."""


class UnsupportedBackend(BackendError):
    """No packet was sent; trying another allowed backend is safe."""


@dataclass(frozen=True)
class Result:
    protocol: str
    external_port: int
    lifetime_seconds: int
    external_ip: str | None = None
    epoch: int | None = None


def encode_nat_pmp(mapping: Mapping, lifetime: int) -> bytes:
    if mapping.protocol != "tcp" or not 0 <= lifetime <= 86400:
        raise ValueError("invalid NAT-PMP TCP mapping or lifetime")
    if lifetime == 0:
        # RFC 6886 deletion identifies the private port. Public port MUST be 0.
        return struct.pack("!BBHHHI", 0, 2, 0, mapping.internal_port, 0, 0)
    return struct.pack("!BBHHHI", 0, 2, 0, mapping.internal_port,
                       mapping.external_port, lifetime)


def decode_nat_pmp(payload: bytes, internal_port: int, deleting: bool = False) -> Result:
    if len(payload) != 16:
        raise BackendError("invalid NAT-PMP response length")
    version, opcode, error, epoch, private, public, lifetime = struct.unpack(
        "!BBHIHHI", payload
    )
    if version != 0 or opcode != 130 or private != internal_port:
        raise BackendError("NAT-PMP response identity mismatch")
    if error:
        raise BackendError(f"NAT-PMP gateway returned result code {error}")
    if deleting:
        if lifetime != 0:
            raise BackendError("NAT-PMP deletion did not grant zero lifetime")
    elif public == 0 or lifetime == 0:
        raise BackendError("NAT-PMP did not grant a usable mapping")
    return Result("nat-pmp", public, lifetime, epoch=epoch)


def _exchange(gateway: str, payload: bytes) -> bytes:
    # Bounded retry schedule; an ambiguous timeout remains an uncertain mutation.
    for timeout in (0.25, 0.5, 1.0, 2.0):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(timeout)
            sock.connect((gateway, 5351))
            try:
                sock.send(payload)
                return sock.recv(256)
            except socket.timeout:
                continue
            except OSError as exc:
                raise BackendError(f"NAT-PMP transport failure: {exc}") from exc
    raise BackendError("NAT-PMP gateway did not respond")


def nat_pmp_request(gateway: str, mapping: Mapping, lifetime: int) -> Result:
    return decode_nat_pmp(_exchange(gateway, encode_nat_pmp(mapping, lifetime)),
                          mapping.internal_port, deleting=lifetime == 0)


def upnp_request(gateway: str, local_address: str,
                 mapping: Mapping, lifetime: int) -> Result:
    try:
        import miniupnpc  # type: ignore[import-not-found]
    except ImportError as exc:
        raise UnsupportedBackend("miniupnpc is not installed") from exc
    client = miniupnpc.UPnP()
    client.discoverdelay = 200
    if client.discover() < 1:
        raise UnsupportedBackend("no UPnP IGD discovered")
    client.selectigd()
    if client.lanaddr != local_address:
        raise UnsupportedBackend("UPnP IGD is not bound to the approved interface")
    # Discovery is not gateway identity verification. No add/remove mutation.
    raise UnsupportedBackend("UPnP IGD writes require a future ownership proof")


class Router:
    """Injectable adapter; replacing this with FakeRouter needs no network."""

    def request(self, backend: str, gateway: str, local_address: str,
                mapping: Mapping, lifetime: int) -> Result:
        if backend == "nat-pmp":
            return nat_pmp_request(gateway, mapping, lifetime)
        if backend == "upnp-igd":
            return upnp_request(gateway, local_address, mapping, lifetime)
        if backend == "pcp":
            raise UnsupportedBackend("PCP MAP not yet implemented")
        raise UnsupportedBackend(f"unknown backend {backend}")

    def release(self, backend: str, gateway: str, local_address: str,
                mapping: Mapping) -> Result:
        if backend == "nat-pmp":
            return nat_pmp_request(gateway, mapping, 0)
        # Never attempt an unsupported backend's deletion.
        raise UnsupportedBackend(f"{backend} release not yet implemented")


def request(backend: str, gateway: str, local_address: str,
            mapping: Mapping, lifetime: int) -> Result:
    """Compatibility entrypoint for callers of the preliminary backend module."""
    return Router().request(backend, gateway, local_address, mapping, lifetime)
