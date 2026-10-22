"""Durable mapping intent reconciliation with conservative, owned cleanup.

"active" means a router reported a grant, NOT a publicly reachable endpoint.
Prepared/uncertain requests are retried against the same gateway and source.
"""

from __future__ import annotations

import logging
import time
from dataclasses import replace
from typing import Any, Callable

from .backends import BackendError, Router, UnsupportedBackend
from .discovery import GatewayError, approved_gateway
from .policy import Mapping, Policy
from .storage import Storage

LOG = logging.getLogger(__name__)
RETRY_AFTER_SECONDS = 30


class ReconcileError(RuntimeError):
    pass


class Agent:
    def __init__(self, storage: Storage, *, router: Router | None = None,
                 gateway_check: Callable[[str], tuple[str, str]] = approved_gateway,
                 clock: Callable[[], float] = time.time):
        self.storage = storage
        self.router = router or Router()
        self.gateway_check = gateway_check
        self.clock = clock

    def inspect(self) -> dict[str, Any]:
        policy = self.storage.policy()
        leases = self.storage.leases()
        return {
            "version": 1, "enabled": policy.enabled,
            "host_id": policy.host_id, "site_id": policy.site_id,
            "configured_gateway": policy.gateway_ipv4,
            "mappings_requested": len(policy.mappings),
            "leases": leases, "reachability": "unverified",
            "cleanup_pending": [
                key for key, value in leases.items()
                if value.get("state") in ("release-prepared", "release-uncertain")
                or not policy.enabled or key not in {m.id for m in policy.mappings}
            ],
            "note": "Router grants are not proof of public Internet reachability",
        }

    def _save(self, leases: dict[str, dict[str, Any]]) -> None:
        self.storage.save_leases(leases)

    @staticmethod
    def _binding_match(record: dict[str, Any], policy: Policy,
                       mapping: Mapping, local: str) -> bool:
        return all((
            record.get("host_id") == policy.host_id,
            record.get("site_id") == policy.site_id,
            record.get("gateway_ipv4") == policy.gateway_ipv4,
            record.get("local_address") == local,
            record.get("internal_port") == mapping.internal_port,
            record.get("requested_external_port") == mapping.external_port,
            record.get("protocol") == mapping.protocol,
        ))

    @staticmethod
    def _stored_mapping(record: dict[str, Any], key: str) -> Mapping:
        external = record.get("assigned_external_port") or record.get("requested_external_port")
        return Mapping(
            id=key, internal_port=record["internal_port"], external_port=external,
            protocol=record["protocol"],
            lifetime_seconds=record.get("requested_lifetime_seconds", 3600),
        )

    def _release(self, leases: dict[str, dict[str, Any]], key: str,
                 record: dict[str, Any], now: float) -> None:
        if record.get("state") == "unsupported":
            del leases[key]
            self._save(leases)
            return
        if now < record.get("retry_after", 0):
            return
        backend = record.get("backend")
        if not backend:
            # No request was sent; safe to forget the prepared local intent.
            del leases[key]
            self._save(leases)
            return
        try:
            _iface, local = self.gateway_check(record["gateway_ipv4"])
        except GatewayError as exc:
            record.update(state="release-uncertain", error=str(exc),
                          retry_after=now + RETRY_AFTER_SECONDS)
            self._save(leases)
            return
        if local != record["local_address"]:
            record.update(state="release-uncertain",
                          error="source address changed; cannot prove mapping ownership",
                          retry_after=now + RETRY_AFTER_SECONDS)
            self._save(leases)
            return
        if record.get("state") != "release-prepared":
            record["state"] = "release-prepared"
            record.pop("error", None)
            self._save(leases)  # durable intent before deletion
        try:
            reply = self.router.release(backend, record["gateway_ipv4"],
                                        local, self._stored_mapping(record, key))
        except (BackendError, OSError) as exc:
            record.update(state="release-uncertain", error=str(exc),
                          retry_after=now + RETRY_AFTER_SECONDS)
            self._save(leases)
            return
        if reply.lifetime_seconds != 0:
            record.update(state="release-uncertain", error="router did not acknowledge removal",
                          retry_after=now + RETRY_AFTER_SECONDS)
            self._save(leases)
            return
        del leases[key]
        self._save(leases)

    def _ensure(self, leases: dict[str, dict[str, Any]], policy: Policy,
                mapping: Mapping, local: str, now: float) -> None:
        key = mapping.id
        record = leases.get(key)
        if record is not None:
            if record.get("state") in ("release-uncertain", "release-prepared"):
                self._release(leases, key, record, now)
                return
            if now < record.get("retry_after", 0):
                return
            if (record.get("state") == "active"
                    and now < record.get("renew_after", 0)):
                return
        else:
            record = {
                "state": "prepared", "host_id": policy.host_id,
                "site_id": policy.site_id, "gateway_ipv4": policy.gateway_ipv4,
                "local_address": local, "internal_port": mapping.internal_port,
                "requested_external_port": mapping.external_port,
                "requested_lifetime_seconds": mapping.lifetime_seconds,
                "protocol": mapping.protocol,
            }
            leases[key] = record
            self._save(leases)

        # A retry of a prepared/uncertain request must preserve the backend.
        backends = ([record["backend"]] if record.get("backend") else policy.backend_order)
        for backend in backends:
            resumed_backend = record.get("backend") == backend
            record.update(state="prepared", backend=backend)
            record.pop("error", None)
            self._save(leases)
            assigned = record.get("assigned_external_port")
            candidate = replace(mapping, external_port=assigned or mapping.external_port)
            try:
                grant = self.router.request(backend, policy.gateway_ipv4,
                                            local, candidate, mapping.lifetime_seconds)
            except UnsupportedBackend as exc:
                if resumed_backend:
                    # An older binary may have made this mapping. Do not drop
                    # durable ownership when its adapter disappears on upgrade.
                    record.update(state="uncertain", error=str(exc),
                                  retry_after=now + RETRY_AFTER_SECONDS)
                    self._save(leases)
                    return
                # A newly attempted unsupported adapter guaranteed no mutation.
                record.pop("backend", None)
                self._save(leases)
                continue
            except (BackendError, OSError) as exc:
                record.update(state="uncertain", error=str(exc),
                              retry_after=now + RETRY_AFTER_SECONDS)
                self._save(leases)
                return

            record.update(
                state="active", backend=backend,
                assigned_external_port=grant.external_port,
                lifetime_seconds=grant.lifetime_seconds,
                granted_at=now,
                renew_after=now + max(30, grant.lifetime_seconds // 2),
                router_epoch=grant.epoch,
            )
            record.pop("retry_after", None)
            record.pop("error", None)
            self._save(leases)
            return

        record.update(state="unsupported", error="no supported backend")
        record.pop("backend", None)
        self._save(leases)

    def reconcile(self) -> dict[str, Any]:
        policy = self.storage.policy()
        leases = self.storage.leases()
        now = self.clock()
        desired = {mapping.id: mapping for mapping in policy.mappings} if policy.enabled else {}
        errors = []

        # Cleanup FIRST, including removed mappings, disabled policies and
        # changed identity/port bindings. Use ORIGINAL persisted binding.
        for key, record in list(leases.items()):
            mapping = desired.get(key)
            keep = False
            if mapping is not None:
                try:
                    _iface, source = self.gateway_check(policy.gateway_ipv4)
                    keep = self._binding_match(record, policy, mapping, source)
                except GatewayError:
                    # Loss of gateway reachability does not revoke ownership.
                    # Preserve existing intent rather than convert it to a
                    # deletion; the enabled-path check below reports the fault.
                    keep = all((
                        record.get("host_id") == policy.host_id,
                        record.get("site_id") == policy.site_id,
                        record.get("gateway_ipv4") == policy.gateway_ipv4,
                        record.get("internal_port") == mapping.internal_port,
                        record.get("requested_external_port") == mapping.external_port,
                        record.get("protocol") == mapping.protocol,
                    ))
            if not keep or record.get("state", "").startswith("release-"):
                self._release(leases, key, record, now)
                if key in leases:
                    errors.append(f"{key}: cleanup incomplete")

        if not policy.enabled:
            if errors:
                LOG.warning("disabled; cleanup still pending: %s", "; ".join(errors))
            return self.inspect()

        try:
            _iface, local = self.gateway_check(policy.gateway_ipv4)
        except GatewayError as exc:
            raise ReconcileError(f"cannot verify configured gateway: {exc}") from exc

        # A conflicting OLD binding must be reclaimed before a NEW one uses
        # the same mapping ID. Do not forget or overwrite cleanup state.
        for mapping in policy.mappings:
            record = leases.get(mapping.id)
            if record and not self._binding_match(record, policy, mapping, local):
                errors.append(f"{mapping.id}: old binding not yet released")
                continue
            self._ensure(leases, policy, mapping, local, now)
        if errors:
            LOG.warning("reconciliation needs operator attention: %s", "; ".join(errors))
        return self.inspect()
