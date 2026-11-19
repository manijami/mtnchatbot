"""Behavior checks for the synthetic incident and trust-boundary fixtures."""
import hashlib
import ipaddress
import unittest
from datetime import datetime, timedelta

from seed import INJECTIONS, INDEXES, encode, events


class SeedTests(unittest.TestCase):
    now = datetime.fromisoformat("2026-11-10T12:00:00+02:00")

    def test_reproducible_range_and_incident(self):
        # Use one-minute cadence here; CLI uses twenty seconds for ~40 MB.
        rows = list(events(self.now, step=60))
        again = hashlib.sha256(b"".join(map(encode, events(self.now, step=60))))
        self.assertEqual(hashlib.sha256(b"".join(map(encode, rows))).digest(), again.digest())
        self.assertEqual(set(r["index"] for r in rows), set(INDEXES))
        self.assertEqual(min(r["time"] for r in rows), (self.now - timedelta(days=7)).timestamp())
        self.assertEqual(max(r["time"] for r in rows), self.now.timestamp())
        changes = [r for r in rows if r["event"].get("action") in ("config_change", "rollback")]
        self.assertEqual([r["event"]["timestamp"][11:16] for r in changes], ["22:40", "23:20"])
        during = [r["event"] for r in rows if changes[0]["time"] < r["time"] < changes[1]["time"] and "status" in r["event"]]
        self.assertEqual({e["host"] for e in during if e["config_version"] == "pool-v2"}, {"pay-api-01", "pay-api-02"})
        self.assertTrue(all(e["status"] >= 500 for e in during if e["config_version"] == "pool-v2"))
        after = [r["event"] for r in rows if r["time"] > changes[1]["time"] and "config_version" in r["event"]]
        self.assertTrue(all(e["config_version"] == "pool-v1" for e in after))
        self.assertEqual([r["event"]["message"] for r in rows if "message" in r["event"]], list(INJECTIONS))
        self.assertEqual(sum(r["event"].get("action") == "demo_alert_evidence" for r in rows), 4)
        for row in rows:
            self.assertTrue(row["event"]["synthetic"])
            if "msisdn" in row["event"]:
                self.assertTrue(row["event"]["msisdn"].startswith("SYNTHETIC-MSISDN-"))
            for field in ("client_ip", "peer_ip"):
                if field in row["event"]:
                    address = ipaddress.ip_address(row["event"][field])
                    self.assertTrue(any(address in ipaddress.ip_network(n) for n in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24")))


if __name__ == "__main__":
    unittest.main()
