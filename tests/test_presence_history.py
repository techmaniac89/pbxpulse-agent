from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pbxsense_agent.presence_history import EndpointLastActiveTracker
from pbxsense_agent.pulse import AmiEndpoint, AmiSnapshot, build_home_payload


def _snapshot(state: str) -> AmiSnapshot:
    return AmiSnapshot(
        reachable=True,
        agent_version="test",
        endpoints=[AmiEndpoint(extension="101", device_state=state)],
    )


def test_last_active_is_final_reachable_observation_and_persists() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory, "endpoint_activity.json")
        tracker = EndpointLastActiveTracker(str(path))
        online_at = datetime(2026, 7, 22, 9, 30, tzinfo=timezone.utc)
        tracker.observe(_snapshot("Reachable"), online_at)
        last_active = tracker.observe(
            _snapshot("Unavailable"), online_at + timedelta(seconds=1)
        )

        assert last_active["101"] == online_at
        assert json.loads(path.read_text(encoding="utf-8"))["101"] == online_at.isoformat()
        assert EndpointLastActiveTracker(str(path)).snapshot()["101"] == online_at


def test_offline_person_payload_includes_last_active_timestamp() -> None:
    last_active = datetime(2026, 7, 22, 9, 30, tzinfo=timezone.utc)
    payload = build_home_payload(
        _snapshot("Unavailable"),
        display_name="PBX",
        extension_names={},
        endpoint_last_active={"101": last_active},
    )

    assert payload["people"][0]["lastActiveAt"] == last_active.isoformat()
