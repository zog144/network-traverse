"""Conservative Linux IPv4 default-gateway discovery."""

from __future__ import annotations

import ipaddress
import socket
import struct
from pathlib import Path


class GatewayError(RuntimeError):
    pass


def default_gateway(path: str | Path = "/proc/net/route") -> tuple[str, str]:
    matches = []
    try:
        lines = Path(path).read_text(encoding="ascii").splitlines()[1:]
        for line in lines:
            cells = line.split()
            if len(cells) < 8:
                continue
            iface, dest, gateway, flags = cells[:4]
            if dest != "00000000" or not (int(flags, 16) & 0x3) == 0x3:
                continue
            matches.append((iface, socket.inet_ntoa(struct.pack("<I", int(gateway, 16)))))
    except (OSError, ValueError) as exc:
        raise GatewayError(f"unable to inspect default route: {exc}") from exc
    if len(matches) != 1:
        raise GatewayError(f"expected exactly one IPv4 default gateway, found {len(matches)}")
    return matches[0]


def local_address_for(gateway: str) -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect((gateway, 5351))
            value = sock.getsockname()[0]
        if not ipaddress.IPv4Address(value).is_private:
            raise GatewayError("source address is not on a private network")
        return value
    except OSError as exc:
        raise GatewayError(f"cannot select local address: {exc}") from exc


def approved_gateway(requested: str) -> tuple[str, str]:
    iface, observed = default_gateway()
    if observed != requested:
        raise GatewayError("configured gateway differs from the current IPv4 default route")
    return iface, local_address_for(requested)
