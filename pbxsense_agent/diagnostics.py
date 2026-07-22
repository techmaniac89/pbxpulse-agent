from __future__ import annotations


def ami_diagnostic_statuses(
    diagnostics: dict,
    *,
    protocol_label: str = "AMI protocol",
) -> tuple[tuple[str, str], ...]:
    """Return progressive AMI checks without impossible Yes/No combinations."""
    if not any(
        key in diagnostics
        for key in ("tcpConnected", "bannerReceived", "loginAccepted")
    ):
        return ()

    tcp_connected = diagnostics.get("tcpConnected") is True
    banner_received = diagnostics.get("bannerReceived") is True
    login_accepted = diagnostics.get("loginAccepted") is True
    port_status = "Reachable" if tcp_connected else "Unreachable"
    if not tcp_connected:
        protocol_status = "Not attempted"
        authentication_status = "Not attempted"
    else:
        protocol_status = (
            "Detected"
            if banner_received
            else "Optional (login accepted)"
            if login_accepted
            else "Not detected"
        )
        authentication_status = "Accepted" if login_accepted else "Rejected"
    return (
        ("PBX port", port_status),
        (protocol_label, protocol_status),
        ("Authentication", authentication_status),
    )


def connector_diagnostic_statuses(
    diagnostics: dict,
) -> tuple[tuple[str, str], ...]:
    """Present protocol checks using the selected connector's vocabulary."""
    pbx_type = str(diagnostics.get("pbxType", "")).casefold()
    if pbx_type == "asterisk":
        return ami_diagnostic_statuses(diagnostics)
    if pbx_type == "grandstream":
        return ami_diagnostic_statuses(
            diagnostics,
            protocol_label="UCM AMI protocol",
        )
    if pbx_type != "freeswitch":
        return ()

    tcp_connected = diagnostics.get("tcpConnected") is True
    login_accepted = diagnostics.get("loginAccepted") is True
    command_accepted = diagnostics.get("commandAccepted") is True
    return (
        ("PBX port", "Reachable" if tcp_connected else "Unreachable"),
        (
            "ESL authentication",
            "Not attempted"
            if not tcp_connected
            else "Accepted"
            if login_accepted
            else "Rejected",
        ),
        (
            "ESL command",
            "Not attempted"
            if not login_accepted
            else "Accepted"
            if command_accepted
            else "Rejected",
        ),
    )
