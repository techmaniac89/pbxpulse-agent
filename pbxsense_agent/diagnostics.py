from __future__ import annotations


def ami_diagnostic_statuses(
    diagnostics: dict,
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
        ("AMI protocol", protocol_status),
        ("Authentication", authentication_status),
    )
