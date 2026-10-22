# network-traverse 0.1 contracts

## Boundary

Phase 0/1 implements **local NAT mapping ownership only**. The agent never runs a
public HTTP service, VNC bridge, SNI gateway, peer discovery, ICE, STUN or TURN.
The sole first-party network side effects are explicitly approved mapping
requests sent to the configured on-site gateway. The phase 1 agent does not
claim Internet-side reachability.

A **site** is a stable operator-defined LAN domain, not a public IP. A **host**
is a Zog host identity furnished by host-identify once integrated. A **mapping**
is a single TCP internal port at the local host, to a router-assigned public
port. The router's reported mapping is an *observation*, not proof of
reachability. A **route** (hostname to host endpoint) belongs to the later SNI
gateway phase and is not yet implemented.

No control-plane agent is allowed to submit arbitrary third-party target IP
addresses. PCP and NAT-PMP use the source address as the internal destination.
For UPnP IGD, the adapter must use the discovered local address, must verify
ownership before update/removal, and requires an additional policy opt-in.

## Security invariants

* **Disabled by default.** Installation/startup creates a disabled policy.
  The agent may inspect it; no router mapping is created by default.
* Enablement requires both "enabled" and a separate inbound-exposure
  acknowledgment, stable host/site ids, a specified on-site gateway and an
  explicit TCP port allowlist.
* The configured gateway must match the Linux IPv4 default next hop in 0.1,
  preventing arbitrary gateway selection. Only the local host's ports map.
* Routes, certificates, VNC/session authorization, DNS updates, and mapping
  publication are outside this phase. No mapping should be enabled for a
  public application before a separate authenticated endpoint is deployed.
* A mutation intent is durably stored **before** a router request. Recovery
  reuses an existing PCP nonce; never blindly deletes unrelated UPnP rules.
  Changes to identity or gateway while a lease remains outstanding are
  rejected until its release has been reconciled.
* The agent is single writer, protected by a process lock; state writes use
  same-directory replace, file fsync and directory fsync. Failures are logged
  and retained rather than silently treating expected router state as real.

## Local interface

The initial local API is a root-owned Unix-domain socket with one read-only
operation, JSON line `{"operation":"inspect"}`. No arbitrary commands or
external network listeners are exposed. Future integrations should use
separately authenticated, bounded control-plane actions.

## Deferred and unverified

Internet-side reachability, CGNAT detection, UPnP IGD vendor behaviors,
router restart recovery, multi-interface, IPv6, TLS gateway and direct WSS
are unverified pending a network test environment. Do not describe
"router_reported" as confirmed inbound reachability.

The first hardware acceptance is intentionally deferred until the planned
local MiniPC network becomes available.
