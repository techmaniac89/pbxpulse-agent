from __future__ import annotations

import json
import socket
from dataclasses import dataclass
from typing import Any

from .pulse import AmiChannel, AmiEndpoint, AmiSnapshot
from .settings import AgentSettings
from .version import AGENT_VERSION


class FreeSwitchError(OSError):
    pass


@dataclass(frozen=True)
class FreeSwitchReply:
    headers: dict[str, str]
    body: str


class FreeSwitchClient:
    name = "freeswitch"
    diagnostics_label = "FreeSWITCH ESL"

    def __init__(self, settings: AgentSettings) -> None:
        self._settings = settings

    def snapshot(self) -> AmiSnapshot:
        try:
            channels = self._channels()
            endpoints = self._endpoints_from_channels(channels)
            return AmiSnapshot(
                reachable=True,
                agent_version=AGENT_VERSION,
                channels=channels,
                endpoints=endpoints,
            )
        except OSError as exc:
            return AmiSnapshot(
                reachable=False,
                agent_version=AGENT_VERSION,
                error=str(exc),
            )

    def diagnostics(self) -> dict:
        result: dict[str, object] = {
            "pbxType": "freeswitch",
            "host": self._settings.freeswitch_host,
            "port": self._settings.freeswitch_port,
            "timeoutSeconds": self._settings.timeout_seconds,
            "tcpConnected": False,
            "loginAccepted": False,
            "commandAccepted": False,
        }

        try:
            with self._connect() as sock:
                result["tcpConnected"] = True
                self._authenticate(sock)
                result["loginAccepted"] = True
                self._api(sock, "status")
                result["commandAccepted"] = True
        except OSError as exc:
            result["error"] = str(exc)

        result["ok"] = result["loginAccepted"] is True
        return result

    def _channels(self) -> list[AmiChannel]:
        with self._connect() as sock:
            self._authenticate(sock)
            raw = self._api(sock, "show channels as json")
        data = _json_object(raw)
        rows = _rows(data)
        return [_channel_from_row(row) for row in rows]

    def _connect(self) -> socket.socket:
        try:
            sock = socket.create_connection(
                (self._settings.freeswitch_host, self._settings.freeswitch_port),
                timeout=self._settings.timeout_seconds,
            )
            sock.settimeout(self._settings.timeout_seconds)
            return sock
        except TimeoutError as exc:
            raise FreeSwitchError(
                "FreeSWITCH ESL TCP connect to "
                f"{self._settings.freeswitch_host}:{self._settings.freeswitch_port} timed out"
            ) from exc
        except OSError as exc:
            raise FreeSwitchError(
                "FreeSWITCH ESL TCP connect to "
                f"{self._settings.freeswitch_host}:{self._settings.freeswitch_port} failed: {exc}"
            ) from exc

    def _authenticate(self, sock: socket.socket) -> None:
        greeting = self._read_reply(sock, phase="FreeSWITCH ESL greeting")
        if greeting.headers.get("content-type", "").lower() != "auth/request":
            raise FreeSwitchError("FreeSWITCH ESL did not request authentication")
        if not self._settings.freeswitch_password:
            raise FreeSwitchError("FreeSWITCH ESL password is not configured")
        self._send(sock, f"auth {self._settings.freeswitch_password}")
        reply = self._read_reply(sock, phase="FreeSWITCH ESL auth")
        if "+OK" not in reply.body:
            raise FreeSwitchError("FreeSWITCH ESL authentication failed")

    def _api(self, sock: socket.socket, command: str) -> str:
        self._send(sock, f"api {command}")
        reply = self._read_reply(sock, phase=f"FreeSWITCH ESL api {command}")
        if reply.body.startswith("-ERR"):
            raise FreeSwitchError(reply.body)
        return reply.body

    def _send(self, sock: socket.socket, command: str) -> None:
        sock.sendall(f"{command}\n\n".encode("utf-8"))

    def _read_reply(self, sock: socket.socket, *, phase: str) -> FreeSwitchReply:
        raw_headers = self._read_until(sock, b"\n\n", phase=phase)
        headers = _parse_headers(raw_headers.decode("utf-8", errors="replace"))
        length = int(headers.get("content-length", "0") or "0")
        body = self._read_exact(sock, length, phase=phase) if length else b""
        return FreeSwitchReply(
            headers=headers,
            body=body.decode("utf-8", errors="replace").strip(),
        )

    def _read_until(self, sock: socket.socket, marker: bytes, *, phase: str) -> bytes:
        chunks: list[bytes] = []
        try:
            while True:
                chunk = sock.recv(1)
                if not chunk:
                    break
                chunks.append(chunk)
                if b"".join(chunks).endswith(marker):
                    break
        except TimeoutError as exc:
            raise FreeSwitchError(f"{phase} timed out") from exc
        return b"".join(chunks)

    def _read_exact(self, sock: socket.socket, length: int, *, phase: str) -> bytes:
        chunks: list[bytes] = []
        remaining = length
        try:
            while remaining > 0:
                chunk = sock.recv(remaining)
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
        except TimeoutError as exc:
            raise FreeSwitchError(f"{phase} body timed out") from exc
        return b"".join(chunks)

    def _endpoints_from_channels(self, channels: list[AmiChannel]) -> list[AmiEndpoint]:
        endpoints: dict[str, AmiEndpoint] = {}
        for channel in channels:
            endpoint = channel.endpoint or channel.extension
            if not endpoint:
                continue
            existing = endpoints.get(endpoint)
            active_channels = (existing.active_channels if existing else 0) + 1
            endpoints[endpoint] = AmiEndpoint(
                extension=endpoint,
                device_state="Reachable",
                active_channels=active_channels,
                label=channel.caller if channel.caller != endpoint else "",
                role="extension",
            )
        return list(endpoints.values())


def _parse_headers(raw: str) -> dict[str, str]:
    headers: dict[str, str] = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    return headers


def _json_object(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    rows = data.get("rows")
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    return []


def _channel_from_row(row: dict[str, Any]) -> AmiChannel:
    name = _string(row, "name", "uuid")
    endpoint = _endpoint_from_channel(name)
    caller_number = _string(row, "cid_num", "cid_number", "caller_id_number")
    caller = _string(row, "cid_name", "caller_id_name", "cid_num")
    destination = _string(row, "dest", "callee_num", "presence_id")
    state = _string(row, "state", "callstate")
    return AmiChannel(
        channel=name,
        extension=destination or endpoint,
        caller=caller or caller_number,
        connected=destination,
        state=state,
        endpoint=endpoint,
        caller_number=caller_number,
        connected_number=destination,
        duration=_string(row, "duration", "call_created_epoch"),
        unique_id=_string(row, "uuid"),
        linked_id=_string(row, "bleg_uuid", "call_uuid", "uuid"),
    )


def _endpoint_from_channel(value: str) -> str:
    if "/" not in value:
        return value
    endpoint = value.rsplit("/", 1)[1]
    return endpoint.split("@", 1)[0].split("-", 1)[0]


def _string(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""
