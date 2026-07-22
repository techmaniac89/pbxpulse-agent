from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from pbxsense_agent.cucm import _merge_inventory_and_registration
from pbxsense_agent.engine import build_engine_signals
from pbxsense_agent.history import read_recent_cucm_calls


class CucmConnectorTest(unittest.TestCase):
    def test_inventory_and_risport_merge_shared_line_devices(self) -> None:
        endpoints = _merge_inventory_and_registration(
            [
                {"extension": "1001", "device_name": "SEP001", "line_description": "Reception"},
                {"extension": "1001", "device_name": "SEP002", "line_description": "Reception"},
                {"extension": "1002", "device_name": "SEP003", "line_description": "Office"},
            ],
            {
                "SEP001": {"status": "UnRegistered", "ip": ""},
                "SEP002": {"status": "Registered", "ip": "10.0.0.12"},
                "SEP003": {"status": "Rejected", "ip": "10.0.0.13"},
            },
        )

        self.assertEqual(len(endpoints), 2)
        self.assertEqual(endpoints[0].device_state, "Reachable")
        self.assertEqual(endpoints[0].ip_address, "10.0.0.12")
        self.assertEqual(endpoints[1].device_state, "Unavailable")

    def test_cdr_and_cmr_are_correlated_into_call_quality(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cdr = Path(directory, "cdr")
            cmr = Path(directory, "cmr")
            cdr.mkdir(); cmr.mkdir()
            self._write(cdr / "cdr.csv", [{
                "globalCallID_callManagerId": "1", "globalCallID_callId": "42",
                "dateTimeOrigination": "1784678400", "duration": "90",
                "callingPartyNumber": "1001", "originalCalledPartyNumber": "2000",
                "finalCalledPartyNumber": "1002", "origDeviceName": "SEP001",
                "destDeviceName": "SEP002",
            }])
            self._write(cmr / "cmr.csv", [{
                "globalCallID_callManagerId": "1", "globalCallID_callId": "42",
                "packetsReceived": "950", "numberPacketsLost": "50",
                "jitter": "35", "latency": "170",
            }])

            calls = read_recent_cucm_calls(str(cdr), str(cmr))

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].destination, "1002")
        self.assertEqual(calls[0].packet_loss_percent, 5.0)
        signals = build_engine_signals(
            endpoints=[], queues=[], recent_calls=calls, voicemails=[],
            security_events=[], extension_names={}, now=calls[0].started_at,
        )
        self.assertIn("call_quality_degradation", {signal["kind"] for signal in signals})

    @staticmethod
    def _write(path: Path, rows: list[dict[str, str]]) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader(); writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()
