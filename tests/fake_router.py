"""Deterministic, in-process NAT-PMP gateway substitute. No network I/O."""

from __future__ import annotations

from dataclasses import replace

from zog.network_traverse.backends import BackendError, Result, UnsupportedBackend


class FakeRouter:
    def __init__(self):
        self.epoch = 100
        self.mapping_by_private = {}
        self.calls = []
        self.drop_next_grant_response = False
        self.drop_next_delete_response = False
        self.fail_backend = set()

    def restart(self):
        self.epoch += 1
        self.mapping_by_private.clear()

    def request(self, backend, gateway, local_address, mapping, lifetime):
        self.calls.append(("request", backend, gateway, local_address,
                           mapping.internal_port, mapping.external_port, lifetime))
        if backend != "nat-pmp" or backend in self.fail_backend:
            raise UnsupportedBackend("fake only implements NAT-PMP")
        key = (local_address, mapping.internal_port, mapping.protocol)
        previous = self.mapping_by_private.get(key)
        if previous:
            assigned = previous
        else:
            occupied = set(self.mapping_by_private.values())
            assigned = mapping.external_port
            if assigned in occupied:
                assigned = next(p for p in range(41000, 42000) if p not in occupied)
            self.mapping_by_private[key] = assigned
        if self.drop_next_grant_response:
            self.drop_next_grant_response = False
            raise BackendError("simulated dropped grant acknowledgment")
        return Result("nat-pmp", assigned, lifetime, epoch=self.epoch)

    def release(self, backend, gateway, local_address, mapping):
        self.calls.append(("release", backend, gateway, local_address,
                           mapping.internal_port, mapping.external_port, 0))
        if backend != "nat-pmp":
            raise UnsupportedBackend("fake only implements NAT-PMP")
        key = (local_address, mapping.internal_port, mapping.protocol)
        self.mapping_by_private.pop(key, None)
        if self.drop_next_delete_response:
            self.drop_next_delete_response = False
            raise BackendError("simulated dropped delete acknowledgment")
        return Result("nat-pmp", 0, 0, epoch=self.epoch)
