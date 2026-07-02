# PBXPulse Agent Connectors

PBXPulse Agent is open source so PBX support should be easy to extend.

A connector observes one PBX family and translates it into PBXPulse concepts.
The app should not know whether the source is Asterisk, FreeSWITCH, 3CX, CUCM,
or something else.

```text
PBX connector
  -> channels, endpoints, trunks, history evidence
  -> Pulse snapshot
  -> Signals
  -> App
```

## Existing Connectors

| PBX | Connector | Status |
| --- | --- | --- |
| Asterisk | `ami.py` | Active calls, endpoints, trunks, CDR history, voicemail |
| FreeSWITCH | `freeswitch.py` | Event Socket connection and active channels |
| Mock | `mock.py` | Development/test fixture |

## Add A Connector

1. Create `agent/pbxpulse_agent/<pbx_name>.py`.
2. Implement a class with:

```python
class ExampleClient:
    name = "example"
    diagnostics_label = "Example PBX"

    def snapshot(self) -> AmiSnapshot:
        ...

    def diagnostics(self) -> dict:
        ...
```

3. Return `AmiSnapshot` from `snapshot()`.
4. Map active calls to `AmiChannel`.
5. Map people/devices/trunks to `AmiEndpoint`.
6. Keep raw PBX details in diagnostics or `technical` evidence, not the first
   app layer.
7. Register the connector in `connector_for_settings()` in `connectors.py`.
8. Add environment variables to `.env.example`.
9. Add installer detection only if the PBX can be detected safely.
10. Add tests for connector selection and at least one mapping example.

The names `AmiSnapshot`, `AmiChannel`, and `AmiEndpoint` are historical from the
first Asterisk connector. Treat them as the Agent's current neutral snapshot
shape until the internal model is renamed.

## Connector Rules

- Never expose raw PBX events as app feed items.
- Prefer stable IDs and grouped Signals.
- Make diagnostics specific and one tap deeper.
- Fail calmly: unreachable PBX should produce an Agent health Signal, not a
  crash.
- Avoid dependencies when the PBX has a simple TCP or HTTP protocol.
- Keep authentication local, tokenized, and private to LAN/VPN by default.

## FreeSWITCH Notes

The first FreeSWITCH connector uses Event Socket Library over TCP:

```text
FREESWITCH_ESL_HOST=127.0.0.1
FREESWITCH_ESL_PORT=8021
FREESWITCH_ESL_PASSWORD=<event_socket password>
```

The installer tries to read the password from:

```text
/etc/freeswitch/autoload_configs/event_socket.conf.xml
```

If the connector can authenticate, it reads `show channels as json` and maps
live calls into the same app model used by Asterisk.
