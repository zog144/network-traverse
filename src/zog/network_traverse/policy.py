"""Versioned, explicit operator policy; no external mapping is implicit."""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from typing import Any

KNOWN_BACKENDS = ("pcp", "nat-pmp", "upnp-igd")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$")


class PolicyError(ValueError):
    """The policy is invalid or does not authorize an operation."""


def _port(value: Any, label: str) -> int:
    if type(value) is not int or not 1 <= value <= 65535:
        raise PolicyError(f"{label} must be an integer between 1 and 65535")
    return value


def _identity(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise PolicyError(f"{label} must be a stable identifier")
    return value


@dataclass(frozen=True)
class Mapping:
    id: str
    internal_port: int
    external_port: int
    protocol: str = "tcp"
    lifetime_seconds: int = 3600

    @classmethod
    def parse(cls, raw: Any) -> "Mapping":
        if not isinstance(raw, dict):
            raise PolicyError("mapping must be an object")
        ident = _identity(raw.get("id"), "mapping id")
        protocol = raw.get("protocol", "tcp")
        if protocol != "tcp":
            raise PolicyError("only TCP is supported in 0.1")
        lifetime = raw.get("lifetime_seconds", 3600)
        if type(lifetime) is not int or not 120 <= lifetime <= 86400:
            raise PolicyError("lifetime_seconds must be between 120 and 86400")
        return cls(ident, _port(raw.get("internal_port"), "internal_port"),
                   _port(raw.get("external_port"), "external_port"),
                   protocol, lifetime)

    def to_dict(self) -> dict[str, Any]:
        return vars(self).copy()


@dataclass(frozen=True)
class Policy:
    enabled: bool
    acknowledge_inbound_exposure: bool
    host_id: str | None
    site_id: str | None
    gateway_ipv4: str | None
    backend_order: tuple[str, ...]
    mappings: tuple[Mapping, ...]
    allow_upnp_igd: bool = False

    @classmethod
    def disabled(cls) -> "Policy":
        return cls(False, False, None, None, None,
                   ("pcp", "nat-pmp"), ())

    @classmethod
    def parse(cls, raw: Any) -> "Policy":
        if not isinstance(raw, dict) or raw.get("version") != 1:
            raise PolicyError("policy must be a version 1 object")
        enabled = raw.get("enabled", False)
        acknowledged = raw.get("acknowledge_inbound_exposure", False)
        allow_upnp = raw.get("allow_upnp_igd", False)
        if any(type(x) is not bool for x in (enabled, acknowledged, allow_upnp)):
            raise PolicyError("enabled, acknowledge_inbound_exposure and allow_upnp_igd must be booleans")
        host_id, site_id = raw.get("host_id"), raw.get("site_id")
        if host_id is not None:
            _identity(host_id, "host_id")
        if site_id is not None:
            _identity(site_id, "site_id")
        gateway = raw.get("gateway_ipv4")
        if gateway is not None:
            try:
                obj = ipaddress.IPv4Address(gateway)
            except (ValueError, TypeError) as exc:
                raise PolicyError("gateway_ipv4 must be an IPv4 address") from exc
            if not obj.is_private:
                raise PolicyError("gateway_ipv4 must be a private/on-site IPv4 address")
            gateway = str(obj)
        backends = raw.get("backend_order", ["pcp", "nat-pmp"])
        if (not isinstance(backends, list) or not backends
                or len(backends) != len(set(map(str, backends)))
                or any(b not in KNOWN_BACKENDS for b in backends)):
            raise PolicyError("backend_order must contain unique supported backend names")
        if "upnp-igd" in backends and not allow_upnp:
            raise PolicyError("upnp-igd requires allow_upnp_igd=true")
        raw_maps = raw.get("mappings", [])
        if not isinstance(raw_maps, list):
            raise PolicyError("mappings must be a list")
        mappings = tuple(Mapping.parse(m) for m in raw_maps)
        if len({m.id for m in mappings}) != len(mappings):
            raise PolicyError("mapping ids must be unique")
        if len({(m.protocol, m.internal_port) for m in mappings}) != len(mappings):
            raise PolicyError("one mapping per protocol and internal port is supported")
        if enabled and (not acknowledged or not host_id or not site_id
                        or not gateway):
            raise PolicyError("enablement requires acknowledgment, host/site identity, gateway and mappings")
        return cls(enabled, acknowledged, host_id, site_id, gateway,
                   tuple(backends), mappings, allow_upnp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1, "enabled": self.enabled,
            "acknowledge_inbound_exposure": self.acknowledge_inbound_exposure,
            "host_id": self.host_id, "site_id": self.site_id,
            "gateway_ipv4": self.gateway_ipv4, "backend_order": list(self.backend_order),
            "allow_upnp_igd": self.allow_upnp_igd,
            "mappings": [m.to_dict() for m in self.mappings],
        }
