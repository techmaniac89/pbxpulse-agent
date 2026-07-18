from __future__ import annotations

import ast
import unittest
from pathlib import Path

from pbxsense_agent.diagnostics import ami_diagnostic_statuses


class MainRouteStructureTest(unittest.TestCase):
    def test_ami_diagnostics_progressively_describe_unattempted_checks(self) -> None:
        self.assertEqual(
            ami_diagnostic_statuses({
                "tcpConnected": False,
                "bannerReceived": False,
                "loginAccepted": False,
            }),
            (
                ("PBX port", "Unreachable"),
                ("AMI protocol", "Not attempted"),
                ("Authentication", "Not attempted"),
            ),
        )

    def test_ami_banner_is_optional_when_login_succeeds(self) -> None:
        self.assertEqual(
            ami_diagnostic_statuses({
                "tcpConnected": True,
                "bannerReceived": False,
                "loginAccepted": True,
            }),
            (
                ("PBX port", "Reachable"),
                ("AMI protocol", "Optional (login accepted)"),
                ("Authentication", "Accepted"),
            ),
        )
    def test_pair_route_has_a_direct_html_return(self) -> None:
        """Keep later route declarations from accidentally splitting pair()."""
        source = Path("pbxsense_agent/main.py").read_text(encoding="utf-8")
        module = ast.parse(source)
        pair_function = next(
            node
            for node in module.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "pair"
        )

        direct_returns = [node for node in pair_function.body if isinstance(node, ast.Return)]

        self.assertTrue(direct_returns, "The /pair route must directly return its rendered page")

    def test_pair_page_keeps_copy_control_for_pairing_text(self) -> None:
        source = Path("pbxsense_agent/main.py").read_text(encoding="utf-8")

        self.assertIn('id="copy-pairing-text"', source)
        self.assertIn('id="copy-feedback"', source)
        self.assertIn("navigator.clipboard.writeText", source)
        self.assertIn("copyFeedback.classList.add('visible')", source)

    def test_empty_paired_app_states_use_the_neutral_gold_card(self) -> None:
        source = Path("pbxsense_agent/main.py").read_text(encoding="utf-8")

        self.assertGreaterEqual(source.count('class="status empty"'), 2)
        self.assertIn(".status.empty", source)

    def test_home_snapshot_exposes_relay_identity_for_live_recreation_detection(self) -> None:
        source = Path("pbxsense_agent/main.py").read_text(encoding="utf-8")

        self.assertIn('payload["connection"]["pushRelayAgentId"]', source)

    def test_paired_app_card_uses_customer_facing_device_details(self) -> None:
        source = Path("pbxsense_agent/main.py").read_text(encoding="utf-8")

        self.assertIn('app_version.split("+", 1)[0]', source)
        self.assertIn('"Model": model or "Not reported"', source)
        self.assertNotIn("model.casefold() != name.strip().casefold()", source)
        self.assertNotIn("Push registration details for this Agent only.", source)


if __name__ == "__main__":
    unittest.main()
