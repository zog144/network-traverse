# Offline NAT mapping acceptance — no router required

Run the pure Python test suite using:

```sh
PYTHONPATH=src python -m unittest discover -s tests -v
```

The suite creates temporary state directories and injects `FakeRouter` into
`Agent`; it **does not** send PCP/NAT-PMP/UPnP packets or open any ports.

The simulator models multiple hosts, port conflicts, dropped grant and
deletion replies, epoch changes on router restart, renewal and persistence.

Tests cover:
* disabled-by-default behavior and distinct exposure acknowledgment;
* router-assigned external ports reused on renewal;
* exact locally owned mapping release and cleanup after disable;
* uncertain operations after dropped responses and bounded retries;
* recovery from crash between router grant and durable active state;
* binding changes preserving cleanup rather than overwriting it;
* RFC 6886 NAT-PMP TCP packet encoding, parsing and deletion.

The fake is not a replacement for real-network tests. It does **not** prove
multi-router interoperability, NAT loopback, WAN reachability, CGNAT, real
NIC/address changes, external DNS propagation or firewall behavior.

All real outbound mapping requests remain disabled until explicitly enabled.
The next release gate remains an isolated network acceptance followed by
actual residential router/MiniPC verification when available.
