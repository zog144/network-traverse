"""RFC 6886 message contract tests without creating network sockets."""

import struct
import unittest

from zog.network_traverse.backends import BackendError, decode_nat_pmp, encode_nat_pmp
from zog.network_traverse.policy import Mapping


class NatPmpPacketTests(unittest.TestCase):
    def setUp(self):
        self.mapping = Mapping("vnc", 8443, 42011)

    def test_tcp_mapping_bytes(self):
        wire = encode_nat_pmp(self.mapping, 3600)
        self.assertEqual(wire, struct.pack("!BBHHHI", 0, 2, 0, 8443, 42011, 3600))
        self.assertEqual(len(wire), 12)

    def test_deletion_zeroes_external_port_and_lifetime(self):
        self.assertEqual(encode_nat_pmp(self.mapping, 0),
                         struct.pack("!BBHHHI", 0, 2, 0, 8443, 0, 0))

    def test_router_response_and_epoch(self):
        response = struct.pack("!BBHIHHI", 0, 130, 0, 157, 8443, 42012, 1800)
        grant = decode_nat_pmp(response, 8443)
        self.assertEqual((grant.external_port, grant.lifetime_seconds, grant.epoch),
                         (42012, 1800, 157))

    def test_invalid_response_rejected(self):
        with self.assertRaises(BackendError):
            decode_nat_pmp(b"short", 8443)
        with self.assertRaises(BackendError):
            decode_nat_pmp(struct.pack("!BBHIHHI", 0, 130, 0, 1, 8444, 42011, 3600), 8443)
        with self.assertRaises(BackendError):
            decode_nat_pmp(struct.pack("!BBHIHHI", 0, 130, 2, 1, 8443, 42011, 3600), 8443)

    def test_deletion_ack_must_have_zero_lifetime(self):
        with self.assertRaises(BackendError):
            decode_nat_pmp(struct.pack("!BBHIHHI", 0, 130, 0, 1, 8443, 42011, 600),
                           8443, deleting=True)
        success = decode_nat_pmp(
            struct.pack("!BBHIHHI", 0, 130, 0, 1, 8443, 0, 0),
            8443, deleting=True
        )
        self.assertEqual(success.lifetime_seconds, 0)


if __name__ == "__main__":
    unittest.main()
