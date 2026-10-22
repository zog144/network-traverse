"""Offline state-machine and simulated-router acceptance: no real router calls."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from zog.network_traverse.agent import Agent
from zog.network_traverse.policy import Policy, PolicyError
from zog.network_traverse.storage import Storage
from fake_router import FakeRouter

HOST = "host-test1"
SITE = "site-test1"
GATEWAY = "192.168.10.1"
LOCAL = "192.168.10.41"


def policy(*, enabled=True, port=8443, external=42011, mapping_id="vnc",
           backend_order=None):
    return {
        "version": 1, "enabled": enabled,
        "acknowledge_inbound_exposure": enabled,
        "host_id": HOST, "site_id": SITE, "gateway_ipv4": GATEWAY,
        "backend_order": backend_order or ["pcp", "nat-pmp"],
        "allow_upnp_igd": False,
        "mappings": [{
            "id": mapping_id, "internal_port": port,
            "external_port": external, "protocol": "tcp",
            "lifetime_seconds": 120,
        }],
    }


class MappingLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.store = Storage(Path(self.temporary.name))
        self.store.initialize()
        self.now = [1000.0]
        self.router = FakeRouter()
        self.make_agent()

    def make_agent(self):
        self.agent = Agent(
            self.store, router=self.router,
            gateway_check=lambda gateway: ("eth0", LOCAL)
                if gateway == GATEWAY else self.fail("unexpected gateway"),
            clock=lambda: self.now[0],
        )

    def enable(self, **kwargs):
        self.store.write_json("policy.json", policy(**kwargs))

    def test_default_disabled_and_no_external_packets(self):
        self.assertFalse(self.store.policy().enabled)
        result = self.agent.reconcile()
        self.assertEqual(result["leases"], {})
        self.assertEqual(self.router.calls, [])
        self.assertEqual(result["reachability"], "unverified")

    def test_opt_in_requires_separate_acknowledgement(self):
        bad = policy()
        bad["acknowledge_inbound_exposure"] = False
        with self.assertRaises(PolicyError):
            Policy.parse(bad)

    def test_grant_assigned_external_port_used_on_renewal(self):
        self.enable()
        # Force router to allocate another external port.
        self.router.mapping_by_private[("192.168.10.52", 9000, "tcp")] = 42011
        first = self.agent.reconcile()["leases"]["vnc"]
        self.assertEqual(first["assigned_external_port"], 41000)
        self.assertEqual(first["backend"], "nat-pmp")
        initial_requests = [c for c in self.router.calls if c[0] == "request"]
        # PCP is deliberately unsupported: record that fallback was tried
        # before NAT-PMP, without treating the safe probe as a successful map.
        self.assertEqual([c[1] for c in initial_requests], ["pcp", "nat-pmp"])
        self.assertEqual(initial_requests[0][5], 42011)
        self.assertEqual(initial_requests[1][5], 42011)
        self.agent.reconcile()
        self.assertEqual(
            [c for c in self.router.calls if c[0] == "request"], initial_requests
        )  # No redundant attempts before the renewal deadline.
        self.now[0] += 70
        self.agent.reconcile()
        renewed_requests = [c for c in self.router.calls if c[0] == "request"]
        self.assertEqual(len(renewed_requests), 3)
        self.assertEqual(renewed_requests[-1][1], "nat-pmp")
        self.assertEqual(renewed_requests[-1][5], 41000)

    def test_disable_releases_only_owned_mapping(self):
        self.enable()
        self.agent.reconcile()
        other = (LOCAL, 6550, "tcp")
        self.router.mapping_by_private[other] = 44001
        self.store.write_json("policy.json", Policy.disabled().to_dict())
        self.assertEqual(self.agent.reconcile()["leases"], {})
        self.assertEqual(self.router.mapping_by_private, {other: 44001})
        self.assertEqual(self.router.calls[-1][0], "release")

    def test_dropped_grant_reply_persists_uncertainty_and_retries(self):
        self.enable()
        self.router.drop_next_grant_response = True
        self.assertEqual(self.agent.reconcile()["leases"]["vnc"]["state"], "uncertain")
        self.assertEqual(len(self.router.mapping_by_private), 1)
        self.assertEqual(self.agent.reconcile()["leases"]["vnc"]["state"], "uncertain")
        self.now[0] += 31
        self.assertEqual(self.agent.reconcile()["leases"]["vnc"]["state"], "active")
        self.assertEqual(len(self.router.mapping_by_private), 1)

    def test_dropped_delete_reply_does_not_forget_ownership(self):
        self.enable()
        self.agent.reconcile()
        self.router.drop_next_delete_response = True
        self.store.write_json("policy.json", Policy.disabled().to_dict())
        result = self.agent.reconcile()
        self.assertEqual(result["cleanup_pending"], ["vnc"])
        self.assertEqual(result["leases"]["vnc"]["state"], "release-uncertain")
        self.assertEqual(self.agent.reconcile()["cleanup_pending"], ["vnc"])
        self.now[0] += 31
        self.assertEqual(self.agent.reconcile()["leases"], {})

    def test_change_of_mapping_does_not_overwrite_pending_cleanup(self):
        self.enable()
        self.agent.reconcile()
        self.router.drop_next_delete_response = True
        self.enable(port=8444)
        first = self.agent.reconcile()["leases"]["vnc"]
        self.assertEqual(first["internal_port"], 8443)
        self.assertEqual(first["state"], "release-uncertain")
        self.assertNotIn((LOCAL, 8444, "tcp"), self.router.mapping_by_private)
        self.now[0] += 31
        self.agent.reconcile()
        # After cleanup, new desired binding can be introduced on next pass.
        self.agent.reconcile()
        self.assertEqual(self.agent.inspect()["leases"]["vnc"]["internal_port"], 8444)

    def test_crash_after_router_grant_replays_prepared_intent(self):
        self.enable()
        original_save = self.store.save_leases
        crash_armed = [True]

        def crash_after_grant(leases):
            if (crash_armed[0] and leases.get("vnc", {}).get("state") == "active"):
                crash_armed[0] = False
                raise RuntimeError("simulated process crash before active-state commit")
            original_save(leases)

        self.store.save_leases = crash_after_grant
        with self.assertRaisesRegex(RuntimeError, "simulated process crash"):
            self.agent.reconcile()
        self.assertEqual(self.store.leases()["vnc"]["state"], "prepared")
        self.store.save_leases = original_save
        self.make_agent()
        self.assertEqual(self.agent.reconcile()["leases"]["vnc"]["state"], "active")
        self.assertEqual(len(self.router.mapping_by_private), 1)

    def test_backend_removal_cannot_forget_existing_mapping(self):
        self.enable()
        self.agent.reconcile()
        self.router.fail_backend.add("nat-pmp")
        self.now[0] += 70
        record = self.agent.reconcile()["leases"]["vnc"]
        self.assertEqual(record["state"], "uncertain")
        self.assertEqual(record["backend"], "nat-pmp")
        self.assertIn((LOCAL, 8443, "tcp"), self.router.mapping_by_private)

    def test_gateway_restart_reestablished_on_next_renewal(self):
        self.enable()
        self.agent.reconcile()
        self.router.restart()
        self.now[0] += 70
        record = self.agent.reconcile()["leases"]["vnc"]
        self.assertEqual(record["router_epoch"], 101)
        self.assertIn((LOCAL, 8443, "tcp"), self.router.mapping_by_private)

    def test_removal_from_policy_releases_mapping(self):
        self.enable()
        self.agent.reconcile()
        changed = policy()
        changed["mappings"] = []
        self.store.write_json("policy.json", changed)
        self.assertEqual(self.agent.reconcile()["leases"], {})

    def test_temporary_gateway_outage_does_not_delete_enabled_mapping(self):
        self.enable()
        self.agent.reconcile()
        saved_calls = len(self.router.calls)

        def down(gateway):
            from zog.network_traverse.discovery import GatewayError
            raise GatewayError("simulated temporary route loss")

        self.agent.gateway_check = down
        from zog.network_traverse.agent import ReconcileError
        with self.assertRaises(ReconcileError):
            self.agent.reconcile()
        self.assertEqual(self.store.leases()["vnc"]["state"], "active")
        self.assertEqual(len(self.router.calls), saved_calls)

    def test_disabled_policy_with_unreachable_gateway_keeps_cleanup(self):
        self.enable()
        self.agent.reconcile()
        self.store.write_json("policy.json", Policy.disabled().to_dict())
        def down(gateway):
            from zog.network_traverse.discovery import GatewayError
            raise GatewayError("simulated offline router")
        self.agent.gateway_check = down
        state = self.agent.reconcile()
        self.assertEqual(state["leases"]["vnc"]["state"], "release-uncertain")
        self.assertEqual(state["cleanup_pending"], ["vnc"])


if __name__ == "__main__":
    unittest.main()
