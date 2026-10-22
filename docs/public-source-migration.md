# Public clean-history source migration boundary

Source-only export of the preliminary disabled-by-default NAT mapping engine.
The original private source snapshot, exact branch history and internal review
evidence remain outside the public Git commit.

The public source does **not** include or require any network policy state,
mapping lease, router UUID/password, controlled domain, host enrollment,
public IP, cloud credential, VNC session ticket, browser proxy or external
certificate. Read-only local `inspect` is not an authenticated Internet API.
NAT-PMP is the only mutating protocol backend in Phase 1 and requires an
explicit acknowledged policy; PCP/UPnP writes are not implemented.

Public Actions may run only the in-process fake-router tests, compile/import,
CLI `--help`, and source/package license checks. Do not run
`reconcile-once` or `serve` as acceptance on a host with router access.

The license grant covers original first-party material; MiniUPnPc is an
optional independently installed external component. Do not confuse the
Python build output with immutable hardware/application acceptance.

Before public `unstable`: per-file hash/provenance and privacy check, legal
scope review, offline tests on Python 3.11/3.12, wheel/sdist, and a fresh
zero-parent public Git root built from only the accepted tree. Separate user GO
is required. First public Actions verification follows the authorized push;
promotion to public `main` must preserve its placeholder history.
