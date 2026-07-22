from __future__ import annotations

import unittest
from pathlib import Path


class InstallerStructureTest(unittest.TestCase):
    def test_docker_setup_reuses_connector_configuration(self) -> None:
        common = Path("scripts/install_common.sh").read_text(encoding="utf-8")
        setup = Path("scripts/setup_docker.sh").read_text(encoding="utf-8")

        self.assertIn('PBXSENSE_CONFIGURE_ONLY:-false', common)
        self.assertIn("configure_agent_env", common)
        self.assertIn("PBXSENSE_CONFIGURE_ONLY=true", setup)
        self.assertIn('docker compose up -d --build', setup)

    def test_installers_print_the_authenticated_pc_link(self) -> None:
        common = Path("scripts/install_common.sh").read_text(encoding="utf-8")
        docker = Path("scripts/setup_docker.sh").read_text(encoding="utf-8")

        self.assertIn("print_admin_link", common)
        self.assertIn("/?token=$token", common)
        self.assertIn("/?token=$token", docker)

    def test_connector_prompt_uses_product_order(self) -> None:
        common = Path("scripts/install_common.sh").read_text(encoding="utf-8")

        self.assertIn(
            "PBX type: asterisk, freeswitch, yeastar, grandstream, cucm, or mock",
            common,
        )


if __name__ == "__main__":
    unittest.main()
