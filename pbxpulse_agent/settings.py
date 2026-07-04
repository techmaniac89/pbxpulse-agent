from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AgentSettings:
    mode: str
    pbx_type: str
    host: str
    port: int
    username: str
    password: str
    freeswitch_host: str
    freeswitch_port: int
    freeswitch_password: str
    freeswitch_cdr_json_path: str
    freeswitch_voicemail_path: str
    threecx_base_url: str
    threecx_deployment: str
    threecx_client_id: str
    threecx_client_secret: str
    threecx_auth_path: str
    threecx_test_path: str
    threecx_active_calls_path: str
    threecx_users_path: str
    threecx_call_history_path: str
    threecx_voicemails_path: str
    display_name: str
    timeout_seconds: float
    extension_names: dict[str, str]
    cdr_csv_path: str
    voicemail_path: str
    timezone: str
    token: str

    @classmethod
    def from_env(cls) -> "AgentSettings":
        mode = os.getenv("PBXPULSE_AGENT_MODE", "").strip().lower()
        pbx_type = _normalize_pbx_type(
            os.getenv("PBXPULSE_PBX_TYPE", mode or "asterisk")
        )
        return cls(
            mode=mode or ("ami" if pbx_type == "asterisk" else pbx_type),
            pbx_type=pbx_type,
            host=os.getenv("ASTERISK_AMI_HOST", "127.0.0.1"),
            port=_env_int("ASTERISK_AMI_PORT", 5038),
            username=os.getenv("ASTERISK_AMI_USERNAME", ""),
            password=os.getenv("ASTERISK_AMI_PASSWORD", ""),
            freeswitch_host=os.getenv("FREESWITCH_ESL_HOST", "127.0.0.1"),
            freeswitch_port=_env_int("FREESWITCH_ESL_PORT", 8021),
            freeswitch_password=os.getenv("FREESWITCH_ESL_PASSWORD", ""),
            freeswitch_cdr_json_path=os.getenv("FREESWITCH_CDR_JSON_PATH", ""),
            freeswitch_voicemail_path=os.getenv("FREESWITCH_VOICEMAIL_PATH", ""),
            threecx_base_url=os.getenv("THREECX_BASE_URL", "").rstrip("/"),
            threecx_deployment=_normalize_3cx_deployment(
                os.getenv("THREECX_DEPLOYMENT", "")
            ),
            threecx_client_id=os.getenv("THREECX_CLIENT_ID", ""),
            threecx_client_secret=os.getenv("THREECX_CLIENT_SECRET", ""),
            threecx_auth_path=os.getenv("THREECX_AUTH_PATH", "/connect/token"),
            threecx_test_path=os.getenv(
                "THREECX_TEST_PATH",
                "/xapi/v1/Defs?$select=Id",
            ),
            threecx_active_calls_path=os.getenv(
                "THREECX_ACTIVE_CALLS_PATH",
                "/callcontrol",
            ),
            threecx_users_path=os.getenv("THREECX_USERS_PATH", "/xapi/v1/Users"),
            threecx_call_history_path=os.getenv(
                "THREECX_CALL_HISTORY_PATH",
                "/xapi/v1/CallHistoryView",
            ),
            threecx_voicemails_path=os.getenv(
                "THREECX_VOICEMAILS_PATH",
                "/xapi/v1/Voicemails",
            ),
            display_name=os.getenv(
                "PBXPULSE_DISPLAY_NAME",
                _default_display_name(pbx_type),
            ),
            timeout_seconds=_env_float(
                "PBXPULSE_CONNECT_TIMEOUT",
                _env_float("ASTERISK_AMI_TIMEOUT", 3),
            ),
            extension_names=_parse_extension_names(
                os.getenv(
                    "PBXPULSE_EXTENSION_NAMES",
                    "",
                )
            ),
            cdr_csv_path=os.getenv(
                "ASTERISK_CDR_CSV_PATH",
                os.getenv(
                    "ASTERISK_CDR_CUSTOM_PATH",
                    "/var/log/asterisk/cdr-csv/Master.csv",
                ),
            ),
            voicemail_path=os.getenv(
                "ASTERISK_VOICEMAIL_PATH",
                "/var/spool/asterisk/voicemail",
            ),
            timezone=os.getenv("PBXPULSE_TIMEZONE", os.getenv("TZ", "")).strip(),
            token=os.getenv("PBXPULSE_AGENT_TOKEN", "").strip(),
        )


def _parse_extension_names(raw: str) -> dict[str, str]:
    names: dict[str, str] = {}
    for chunk in raw.split(","):
        if "=" not in chunk:
            continue
        extension, name = chunk.split("=", 1)
        extension = extension.strip()
        name = name.strip()
        if extension and name:
            names[extension] = name
    return names


def _normalize_pbx_type(raw: str) -> str:
    normalized = raw.strip().lower().replace("-", "").replace("_", "")
    return {
        "ami": "asterisk",
        "asteriskami": "asterisk",
        "asterisk": "asterisk",
        "freepbx": "asterisk",
        "issabel": "asterisk",
        "vitalpbx": "asterisk",
        "fs": "freeswitch",
        "freeswitch": "freeswitch",
        "fusionpbx": "freeswitch",
        "3cx": "3cx",
        "threecx": "3cx",
        "mock": "mock",
    }.get(normalized, normalized or "asterisk")


def _normalize_3cx_deployment(raw: str) -> str:
    normalized = raw.strip().lower().replace("-", "").replace("_", "")
    if normalized in {"local", "selfhosted", "selfhost", "onprem", "onpremise", "onpremises"}:
        return "local"
    if normalized in {"cloud", "hosted", "saas", "3cxhosted"}:
        return "cloud"
    return ""


def _default_display_name(pbx_type: str) -> str:
    return {
        "asterisk": "Asterisk",
        "freeswitch": "FreeSWITCH",
        "3cx": "3CX",
        "mock": "Mock PBX",
    }.get(pbx_type, "PBX")


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default
