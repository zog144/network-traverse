# Network-traverse Phase 1 checkpoint — 2026-10-21

Branch: `unstable`; hardware and WAN acceptance: **OPEN**.

## Implemented

1. Default-disabled, explicitly acknowledged operator policy.
2. Fsynced mutation intent before sending NAT-PMP requests.
3. NAT-PMP TCP MAP/renew/delete requests, exact-response validation,
   assigned-port reuse on renewal, and retryable uncertain states.
4. Cleanup of removed mappings and disabled policy, with original binding
   retained until acknowledged. Unknown source-address changes block cleanup.
5. Supervised reconciliation tick, local inspection and single-writer state.
6. In-process fake router plus stdlib unit tests for lease conflicts, dropped
   replies, reboot, crash windows, disappearance of a backend and cleanup.

## Acceptance status

* Source published: YES.
* Syntax/stdlib tests executed in this session: **NO**.
* GitHub Actions used: **NO**.
* Physical NAT router contacted: **NO**.
* Public IP/CGNAT/firewall verification: **NO**.
* No production enablement: YES (disabled-by-default policy retained).

## Known limitations / next work

* Not a certified production lease manager. Simulated tests need execution
  before any deployment claim.
* PCP MAP and UPnP mapping/delete are not implemented.
* NAT-PMP has no PCP-style nonce; deletion is scoped by original source IP,
  transport and internal port, which must remain exclusively allocated to
  this service during the operation. Independent on-host mapping owners must
  be coordinated before exposing a shared internal listener.
* Router uptime epoch is recorded but full discontinuity detection is not
  implemented; mappings are attempted again on scheduled renewal.
* Missing local gateway/source binding prevents safe deletion; such records
  remain visible for operator remediation or known router-side lease expiry.
* Periodic reconciliation is time-based, not event-triggered by policy edits.
* No automatic CGNAT detection or external reachability proof.
* No HTTPS/SNI gateway, WSS admission, workspace tickets, host-discover,
  network-register, or certify-manage integrations.
* No live router test network until the planned local MiniPC acceptance.

## Next validation

Run `PYTHONPATH=src python -m unittest discover -s tests -v` on a sandbox
or public Actions runner when eligible. Resolve all failures and report
exact revision/evidence. Continue with PCP adapter and integration contracts
only after inspecting the test results. Do not promote this checkpoint to
production-ready.
