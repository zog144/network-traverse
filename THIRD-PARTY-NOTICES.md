# Third-party notices — network-traverse development source

Original first-party network-traverse Python source, tests and documentation are
provided under **BSD-3-Clause OR GPL-3.0-only**; see LICENSE, COPYRIGHT and
both complete legal texts under LICENSES/.

The current base package uses the Python standard library; the optional
`upnp` extra selects the separately installed `miniupnpc>=2.2` package.
Its Python extension, C library, upstream sources and any transitive or native
dependencies retain their independent notices and licenses. No such compiled
dependency is vendored or bundled in this Git export.

The Linux kernel network stack, host-router device firmware, NAT-PMP/PCP
protocol documentation, UPnP IGD services, physical routers and future
third-party DNS/TLS libraries are not relicensed here. This source export
does not contain or authorize host network credentials, NAT policy or live
router mappings. A later actual binary/immutable application view must perform
a separate exact installed-dependency license inventory.

Publication and offline fake-router test results do **not** certify reachable
NAT mappings, CGNAT detection, TLS/WSS admission, active VNC bridging, or safe
production port exposure.
