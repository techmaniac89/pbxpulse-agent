from __future__ import annotations

import base64
import ssl
import time
from collections import defaultdict
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

from .pulse import AmiEndpoint, AmiSnapshot
from .settings import AgentSettings
from .version import AGENT_VERSION


class CucmError(OSError):
    pass


class CucmClient:
    """Read-only CUCM inventory and registration connector.

    AXL supplies directory-number/device ownership; RisPort70 supplies the
    cluster-wide registration snapshot. Live calls deliberately remain empty
    until the separate JTAPI milestone.
    """

    name = "cucm"
    diagnostics_label = "CUCM AXL/RisPort"

    def __init__(self, settings: AgentSettings) -> None:
        self._settings = settings
        self._cached_snapshot: AmiSnapshot | None = None
        self._refresh_after = 0.0

    def snapshot(self) -> AmiSnapshot:
        if self._cached_snapshot and time.monotonic() < self._refresh_after:
            return self._cached_snapshot
        try:
            inventory = self._directory_inventory()
            registration = self._registration_status()
            endpoints = _merge_inventory_and_registration(inventory, registration)
            result = AmiSnapshot(
                reachable=True,
                agent_version=AGENT_VERSION,
                endpoints=endpoints,
            )
        except OSError as exc:
            result = AmiSnapshot(
                reachable=False, agent_version=AGENT_VERSION, error=str(exc)
            )
        self._cached_snapshot = result
        # RisPort is a bulk real-time query; avoid turning the one-second app
        # refresh into a one-second CUCM SOAP poll.
        self._refresh_after = time.monotonic() + 10
        return result

    def diagnostics(self) -> dict[str, object]:
        result: dict[str, object] = {
            "pbxType": "cucm",
            "host": self._settings.cucm_host,
            "port": 8443,
            "apiVersion": self._settings.cucm_axl_version,
            "tlsVerification": self._settings.cucm_verify_tls,
            "credentialsConfigured": bool(
                self._settings.cucm_username and self._settings.cucm_password
            ),
            "axlReachable": False,
            "risPortReachable": False,
            "liveCallsAvailable": False,
        }
        try:
            self._directory_inventory()
            result["axlReachable"] = True
        except OSError as exc:
            result["axlError"] = str(exc)
        try:
            self._registration_status()
            result["risPortReachable"] = True
        except OSError as exc:
            result["risPortError"] = str(exc)
        result["ok"] = (
            result["axlReachable"] is True and result["risPortReachable"] is True
        )
        result["message"] = (
            "CUCM inventory and registration services are reachable. Live calls require the later JTAPI connector."
            if result["ok"]
            else "CUCM AXL or RisPort needs attention."
        )
        return result

    def _directory_inventory(self) -> list[dict[str, str]]:
        query = (
            "select d.name as device_name, d.description as device_description, "
            "n.dnorpattern as extension, n.description as line_description "
            "from device d, devicenumplanmap m, numplan n "
            "where m.fkdevice=d.pkid and m.fknumplan=n.pkid and d.tkclass=1"
        )
        body = f"""
          <axl:executeSQLQuery xmlns:axl="http://www.cisco.com/AXL/API/{self._settings.cucm_axl_version}">
            <sql>{_xml_escape(query)}</sql>
          </axl:executeSQLQuery>
        """
        root = self._soap("/axl/", body, f"CUCM:DB ver={self._settings.cucm_axl_version} executeSQLQuery")
        rows: list[dict[str, str]] = []
        for row in _elements(root, "row"):
            values = {_local(child.tag): (child.text or "").strip() for child in row}
            extension = values.get("extension", "")
            device_name = values.get("device_name", "")
            if extension and device_name:
                rows.append(values)
        return rows

    def _registration_status(self) -> dict[str, dict[str, str]]:
        body = """
          <ns:SelectCmDevice xmlns:ns="http://schemas.cisco.com/ast/soap">
            <ns:StateInfo></ns:StateInfo>
            <ns:CmSelectionCriteria>
              <ns:MaxReturnedDevices>1000</ns:MaxReturnedDevices>
              <ns:DeviceClass>Phone</ns:DeviceClass>
              <ns:Model>255</ns:Model><ns:Status>Any</ns:Status>
              <ns:NodeName></ns:NodeName>
              <ns:SelectBy>Name</ns:SelectBy>
              <ns:SelectItems><ns:item><ns:Item>*</ns:Item></ns:item></ns:SelectItems>
              <ns:Protocol>Any</ns:Protocol><ns:DownloadStatus>Any</ns:DownloadStatus>
            </ns:CmSelectionCriteria>
          </ns:SelectCmDevice>
        """
        root = self._soap(
            "/realtimeservice2/services/RISService70",
            body,
            "SelectCmDevice",
        )
        devices: dict[str, dict[str, str]] = {}
        for device in _elements(root, "CmDevice"):
            name = _child_text(device, "Name")
            if not name:
                continue
            ip = ""
            ip_nodes = _elements(device, "IPAddress")
            if ip_nodes:
                ip = _child_text(ip_nodes[0], "IP") or (ip_nodes[0].text or "").strip()
            devices[name] = {
                "status": _child_text(device, "Status"),
                "ip": ip,
                "model": _child_text(device, "Model"),
            }
        return devices

    def _soap(self, path: str, operation: str, action: str) -> ET.Element:
        if not self._settings.cucm_host:
            raise CucmError("CUCM host is not configured")
        if not self._settings.cucm_username or not self._settings.cucm_password:
            raise CucmError("CUCM application-user credentials are not configured")
        envelope = f"""<?xml version="1.0" encoding="UTF-8"?>
          <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
            <soapenv:Header/><soapenv:Body>{operation}</soapenv:Body>
          </soapenv:Envelope>""".encode("utf-8")
        credential = base64.b64encode(
            f"{self._settings.cucm_username}:{self._settings.cucm_password}".encode()
        ).decode("ascii")
        request = Request(
            f"https://{self._settings.cucm_host}:8443{path}",
            data=envelope,
            method="POST",
            headers={
                "Authorization": f"Basic {credential}",
                "Content-Type": "text/xml; charset=utf-8",
                "SOAPAction": f'"{action}"',
                "User-Agent": "PBXSense-Agent",
            },
        )
        context = None if self._settings.cucm_verify_tls else ssl._create_unverified_context()
        try:
            with urlopen(request, timeout=self._settings.timeout_seconds, context=context) as response:
                return ET.fromstring(response.read())
        except HTTPError as exc:
            raise CucmError(f"CUCM SOAP request failed: HTTP {exc.code}") from exc
        except (URLError, TimeoutError, ET.ParseError, ssl.SSLError) as exc:
            raise CucmError(f"CUCM SOAP request failed: {exc}") from exc


def _merge_inventory_and_registration(
    inventory: list[dict[str, str]], registration: dict[str, dict[str, str]]
) -> list[AmiEndpoint]:
    lines: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in inventory:
        lines[row["extension"]].append(row)
    endpoints: list[AmiEndpoint] = []
    for extension, rows in sorted(lines.items()):
        states = [registration.get(row["device_name"], {}) for row in rows]
        registered = any(state.get("status", "").lower() == "registered" for state in states)
        label = next(
            (row.get("line_description", "") or row.get("device_description", "") for row in rows
             if row.get("line_description", "") or row.get("device_description", "")),
            "",
        )
        ip = next((state.get("ip", "") for state in states if state.get("ip")), "")
        endpoints.append(AmiEndpoint(
            extension=extension,
            number=extension,
            label=label,
            device_state="Reachable" if registered else "Unavailable",
            ip_address=ip,
        ))
    return endpoints


def _elements(root: ET.Element, local_name: str) -> list[ET.Element]:
    return [element for element in root.iter() if _local(element.tag) == local_name]


def _child_text(element: ET.Element, local_name: str) -> str:
    for child in element.iter():
        if _local(child.tag) == local_name:
            return (child.text or "").strip()
    return ""


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _xml_escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
