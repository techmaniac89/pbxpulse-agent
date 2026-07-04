from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any

from .history import CdrCall, VoicemailMessage
from .pulse import AmiChannel, AmiEndpoint, AmiSnapshot
from .settings import AgentSettings
from .version import AGENT_VERSION


class ThreeCxError(OSError):
    pass


class ThreeCxClient:
    name = "3cx"
    diagnostics_label = "3CX API"

    def __init__(self, settings: AgentSettings) -> None:
        self._settings = settings

    def snapshot(self) -> AmiSnapshot:
        try:
            token = self._access_token()
            active_calls = self._get_json(self._settings.threecx_active_calls_path, token)
            users = self._optional_items(self._settings.threecx_users_path, token)
            history = self._optional_items(self._settings.threecx_call_history_path, token)
            voicemails = self._optional_items(self._settings.threecx_voicemails_path, token)
            channels = _channels_from_callcontrol(active_calls)
            return AmiSnapshot(
                reachable=True,
                agent_version=AGENT_VERSION,
                channels=[channel for channel in channels if channel.channel],
                endpoints=_endpoints_from_users(users, channels),
                recent_calls=[_cdr_call_from_history(item) for item in history],
                voicemails=[_voicemail_from_row(item) for item in voicemails],
            )
        except OSError as exc:
            return AmiSnapshot(
                reachable=False,
                agent_version=AGENT_VERSION,
                error=str(exc),
            )

    def diagnostics(self) -> dict:
        result: dict[str, object] = {
            "pbxType": "3cx",
            "deployment": self._settings.threecx_deployment,
            "baseUrl": self._settings.threecx_base_url,
            "authPath": self._settings.threecx_auth_path,
            "testPath": self._settings.threecx_test_path,
            "activeCallsPath": self._settings.threecx_active_calls_path,
            "usersPath": self._settings.threecx_users_path,
            "callHistoryPath": self._settings.threecx_call_history_path,
            "voicemailsPath": self._settings.threecx_voicemails_path,
            "timeoutSeconds": self._settings.timeout_seconds,
            "baseUrlConfigured": bool(self._settings.threecx_base_url),
            "clientIdConfigured": bool(self._settings.threecx_client_id),
            "clientSecretConfigured": bool(self._settings.threecx_client_secret),
            "loginAccepted": False,
            "quickTestReadable": False,
            "activeCallsReadable": False,
            "usersReadable": False,
        }

        try:
            token = self._access_token()
            result["loginAccepted"] = True
            try:
                _data, headers = self._get_json_with_headers(
                    self._settings.threecx_test_path,
                    token,
                )
                result["quickTestReadable"] = True
                system_version = _header_value(
                    headers,
                    "x-pbx-version",
                    "x-3cx-version",
                    "x-3cx-system-version",
                )
                if system_version:
                    result["systemVersion"] = system_version
            except OSError as exc:
                result["quickTestError"] = str(exc)
            result["activeCallsCount"] = len(
                _channels_from_callcontrol(
                    self._get_json(self._settings.threecx_active_calls_path, token)
                )
            )
            result["activeCallsReadable"] = True
            try:
                result["usersCount"] = len(
                    _items(self._get_json(self._settings.threecx_users_path, token))
                )
                result["usersReadable"] = True
            except OSError as exc:
                result["usersError"] = str(exc)
            try:
                result["callHistoryCount"] = len(
                    _items(self._get_json(self._settings.threecx_call_history_path, token))
                )
                result["callHistoryReadable"] = True
            except OSError as exc:
                result["callHistoryReadable"] = False
                result["callHistoryError"] = str(exc)
            try:
                result["voicemailsCount"] = len(
                    _items(self._get_json(self._settings.threecx_voicemails_path, token))
                )
                result["voicemailsReadable"] = True
            except OSError as exc:
                result["voicemailsReadable"] = False
                result["voicemailsError"] = str(exc)
        except OSError as exc:
            result["error"] = str(exc)

        result["ok"] = result["loginAccepted"] is True and result["activeCallsReadable"] is True
        return result

    def _access_token(self) -> str:
        if not self._settings.threecx_base_url:
            raise ThreeCxError("3CX base URL is not configured")
        if not self._settings.threecx_client_id:
            raise ThreeCxError("3CX client ID is not configured")
        if not self._settings.threecx_client_secret:
            raise ThreeCxError("3CX client secret is not configured")

        payload = urllib.parse.urlencode(
            {
                "grant_type": "client_credentials",
                "client_id": self._settings.threecx_client_id,
                "client_secret": self._settings.threecx_client_secret,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            self._url(self._settings.threecx_auth_path),
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        data = self._request_json(request, phase="3CX authentication")
        token = _string(data, "access_token", "accessToken", "token")
        if not token:
            raise ThreeCxError("3CX authentication response did not include an access token")
        return token

    def _get_json(self, path: str, token: str) -> Any:
        data, _headers = self._get_json_with_headers(path, token)
        return data

    def _get_json_with_headers(
        self,
        path: str,
        token: str,
    ) -> tuple[Any, dict[str, str]]:
        request = urllib.request.Request(
            self._url(path),
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            method="GET",
        )
        return self._request_json_with_headers(request, phase=f"3CX GET {path}")

    def _optional_items(self, path: str, token: str) -> list[dict[str, Any]]:
        try:
            return _items(self._get_json(path, token))
        except OSError:
            return []

    def _request_json(self, request: urllib.request.Request, *, phase: str) -> Any:
        data, _headers = self._request_json_with_headers(request, phase=phase)
        return data

    def _request_json_with_headers(
        self,
        request: urllib.request.Request,
        *,
        phase: str,
    ) -> tuple[Any, dict[str, str]]:
        try:
            with urllib.request.urlopen(
                request,
                timeout=self._settings.timeout_seconds,
            ) as response:
                raw = response.read().decode("utf-8", errors="replace")
                headers = {key.lower(): value for key, value in response.headers.items()}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace").strip()
            raise ThreeCxError(f"{phase} failed with HTTP {exc.code}: {detail}") from exc
        except TimeoutError as exc:
            raise ThreeCxError(f"{phase} timed out") from exc
        except OSError as exc:
            raise ThreeCxError(f"{phase} failed: {exc}") from exc

        try:
            return (json.loads(raw) if raw else {}), headers
        except json.JSONDecodeError as exc:
            raise ThreeCxError(f"{phase} returned invalid JSON") from exc

    def _url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        if not path.startswith("/"):
            path = f"/{path}"
        return f"{self._settings.threecx_base_url}{path}"


def _items(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if not isinstance(data, dict):
        return []
    for key in ("value", "items", "results", "data"):
        value = data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _channels_from_callcontrol(data: Any) -> list[AmiChannel]:
    rows: list[dict[str, Any]] = []
    for item in _items(data):
        participants = item.get("participants")
        if isinstance(participants, list):
            for participant in participants:
                if not isinstance(participant, dict):
                    continue
                merged = dict(participant)
                merged.setdefault("entity_dn", item.get("dn"))
                merged.setdefault("entity_type", item.get("type"))
                rows.append(merged)
        else:
            rows.append(item)
    return [_channel_from_call(row) for row in rows]


def _channel_from_call(call: dict[str, Any]) -> AmiChannel:
    channel = _string(call, "callid", "callId", "id", "legid", "uuid", "uniqueId")
    caller_number = _string(
        call,
        "party_caller_id",
        "party_dn",
        "originated_by_dn",
        "callerNumber",
        "caller_number",
        "fromNumber",
        "from_number",
        "caller",
        "from",
    )
    caller = _string(
        call,
        "party_caller_name",
        "callerName",
        "caller_name",
        "fromName",
        "from_name",
    )
    connected_number = _string(
        call,
        "party_dn",
        "on_behalf_of_dn",
        "referred_by_dn",
        "calleeNumber",
        "callee_number",
        "toNumber",
        "to_number",
        "destination",
        "to",
    )
    connected = _string(
        call,
        "calleeName",
        "callee_name",
        "toName",
        "to_name",
        "party_dn",
    )
    endpoint = _string(call, "dn", "entity_dn", "extension", "sourceDn", "source", "owner")
    if not endpoint:
        endpoint = caller_number if caller_number.isdigit() else connected_number
    return AmiChannel(
        channel=channel or f"3cx-{caller_number}-{connected_number}",
        extension=connected_number or endpoint,
        caller=caller or caller_number,
        connected=connected or connected_number,
        state=_string(call, "status", "state", "callState", "call_state"),
        endpoint=endpoint,
        caller_number=caller_number,
        connected_number=connected_number,
        duration=_string(call, "duration", "durationSeconds", "talkingSince"),
        unique_id=channel,
        linked_id=_string(call, "linkedId", "linked_id", "callId", "callid", "id"),
    )


def _endpoints_from_users(
    users: list[dict[str, Any]],
    channels: list[AmiChannel],
) -> list[AmiEndpoint]:
    active_counts: dict[str, int] = {}
    for channel in channels:
        endpoint = channel.endpoint or channel.extension
        if endpoint:
            active_counts[endpoint] = active_counts.get(endpoint, 0) + 1

    endpoints: dict[str, AmiEndpoint] = {}
    for user in users:
        extension = _string(user, "number", "extension", "dn", "id")
        if not extension:
            continue
        endpoints[extension] = AmiEndpoint(
            extension=extension,
            device_state=_presence_state(user),
            active_channels=active_counts.get(extension, 0),
            label=_user_label(user),
            role="extension",
        )

    for extension, active_channels in active_counts.items():
        existing = endpoints.get(extension)
        endpoints[extension] = AmiEndpoint(
            extension=extension,
            device_state=existing.device_state if existing else "Reachable",
            active_channels=active_channels,
            label=existing.label if existing else "",
            role=existing.role if existing else "extension",
        )

    return list(endpoints.values())


def _cdr_call_from_history(row: dict[str, Any]) -> CdrCall:
    disposition = _call_disposition(row)
    destination = _string(
        row,
        "calleeNumber",
        "callee_number",
        "toNumber",
        "to_number",
        "destination",
        "dst",
        "to",
    )
    last_app = _string(row, "lastApp", "last_app", "action", "segmentType", "type")
    last_data = _string(row, "lastData", "last_data", "ivr", "ivrName", "queueName")
    context = _string(row, "context", "route", "routing", "callType", "type")
    if _looks_like_ivr_row(row):
        context = context or "ivr"
        last_app = last_app or "Answer"
        last_data = last_data or "ivr"
        destination = destination or "s"
        disposition = "ANSWERED"
    return CdrCall(
        source=_string(
            row,
            "callerNumber",
            "caller_number",
            "fromNumber",
            "from_number",
            "source",
            "src",
            "from",
        ),
        destination=destination,
        disposition=disposition,
        started_at=_parse_datetime(
            _string(row, "startedAt", "startTime", "start_time", "date", "time")
        ),
        duration_seconds=_parse_duration(
            _string(row, "durationSeconds", "duration_seconds", "duration", "talkTime")
        ),
        context=context,
        channel=_string(row, "id", "callId", "callid", "uniqueId"),
        destination_channel=_string(row, "destinationChannel", "answeredBy", "agent"),
        last_app=last_app,
        last_data=last_data,
    )


def _voicemail_from_row(row: dict[str, Any]) -> VoicemailMessage:
    return VoicemailMessage(
        mailbox=_string(
            row,
            "mailbox",
            "extension",
            "dn",
            "recipient",
            "recipientNumber",
            "toNumber",
        ),
        caller=_string(
            row,
            "callerName",
            "caller",
            "callerNumber",
            "fromName",
            "fromNumber",
        )
        or "A caller",
        created_at=_parse_datetime(
            _string(row, "createdAt", "timestamp", "date", "time", "receivedAt")
        ),
    )


def _user_label(user: dict[str, Any]) -> str:
    direct = _string(user, "displayName", "name", "fullName")
    if direct:
        return direct
    name = " ".join(
        part
        for part in (
            _string(user, "firstName"),
            _string(user, "lastName"),
        )
        if part
    )
    return name or _string(user, "email", "emailAddress")


def _presence_state(user: dict[str, Any]) -> str:
    raw = _string(user, "status", "presence", "profileStatus", "registrarStatus")
    if not raw:
        return "Reachable"
    normalized = raw.lower()
    if any(marker in normalized for marker in ("away", "dnd", "busy", "offline")):
        return raw
    return "Reachable" if "available" in normalized else raw


def _call_disposition(row: dict[str, Any]) -> str:
    raw = _string(row, "disposition", "result", "status", "state", "reason")
    normalized = raw.lower()
    if any(marker in normalized for marker in ("miss", "no answer", "unanswered")):
        return "NO ANSWER"
    if "busy" in normalized:
        return "BUSY"
    if any(marker in normalized for marker in ("fail", "error")):
        return "FAILED"
    if any(marker in normalized for marker in ("answer", "complete", "connected", "talk")):
        return "ANSWERED"
    return raw.upper() if raw else "ANSWERED"


def _looks_like_ivr_row(row: dict[str, Any]) -> bool:
    haystack = " ".join(str(value).lower() for value in row.values() if value is not None)
    return any(marker in haystack for marker in ("ivr", "digital receptionist", "menu"))


def _parse_datetime(raw: str) -> datetime | None:
    value = raw.strip()
    if not value:
        return None
    if value.isdigit():
        try:
            return datetime.fromtimestamp(int(value))
        except (OSError, ValueError):
            return None
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).replace(tzinfo=None)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%d/%m/%Y %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _parse_duration(raw: str) -> int:
    value = raw.strip()
    if not value:
        return 0
    try:
        return int(float(value))
    except ValueError:
        pass
    parts = value.split(":")
    if all(part.isdigit() for part in parts):
        total = 0
        for part in parts:
            total = total * 60 + int(part)
        return total
    return 0


def _string(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    lowered = {str(key).lower(): value for key, value in row.items()}
    for key in keys:
        value = lowered.get(key.lower())
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _header_value(headers: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = headers.get(key.lower())
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""
