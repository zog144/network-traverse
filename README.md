# network-traverse

Zog host-local, opt-in network traversal service.

**Status: Phase 0 and preliminary Phase 1 implementation on `unstable`.**
No Internet-facing service is installed. Router hardware and WAN reachability
are not verified. Mapping functionality is **disabled by default**.

## Current functionality

* Namespaced Python package: `zog.network_traverse`.
* Explicit policy with separate inbound-exposure acknowledgment.
* Durable mapping intent, single-writer lock and fsynced state changes.
* Linux IPv4 default gateway and source-address validation.
* NAT-PMP TCP map, renewal (using assigned public port) and owned deletion.
* Persistent prepared/active/uncertain/release states with retry backoff.
* Cleanup when a mapping is removed or policy disabled, retaining unresolved
  cleanup rather than silently forgetting potential router state.
* Periodic reconciliation with configurable interval and local read-only
  Unix socket inspection.
* In-process fake gateway and stdlib `unittest` simulation tests.
* PCP and UPnP IGD **writes not implemented**; UPnP discovery is gated and
  cannot publish a mapping.

## Safe local operations

```sh
network-traverse initialize-only
network-traverse inspect
network-traverse --state-dir /state/network-traverse reconcile-once
network-traverse --state-dir /state/network-traverse serve --interval 30
```

`initialize-only` creates a disabled policy and empty mapping state.
`inspect` reports effective state without contacting a router.

**Do not enable a mapping** to VNC, station-access, box-control, or any other
service until an independent authenticated TLS endpoint and deployment
acceptance are completed. An `active` record means only that the router
returned a mapping grant; it is not a confirmed accessible network path.

## Offline tests

```sh
PYTHONPATH=src python -m unittest discover -s tests -v
```

The tests simulate a gateway entirely in-process. They do not send NAT
management packets or require a MiniPC or AWS account. They have been
**committed but not yet executed** by this implementation session.

See [architecture](docs/architecture.md),
[offline acceptance](docs/offline-acceptance.md) and
[implementation checkpoint](docs/checkpoint-2026-10-21.md).

## Public development source boundary

This repository's public-source export is independent of any live NAT/router
installation, externally reachable endpoint, cloud or registrar credentials,
certificate authority, websocket proxy, host enrollment, DNS configuration,
or issuance of a public-facing service. A public Git ref permits source review
and offline test execution only. No Zog product release or native hardware
acceptance is implied by a source publication.

Original Zog-owned source is offered under **BSD-3-Clause OR GPL-3.0-only**;
see [LICENSE](LICENSE), [complete license texts](LICENSES/) and
[third-party notices](THIRD-PARTY-NOTICES.md). External optional `miniupnpc`
remains independently licensed and is **not bundled**. There are no Zog
public companion source pins selected in this preliminary phase.
