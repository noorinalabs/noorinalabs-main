#!/usr/bin/env python3
"""PreToolUse hook: Validate VPS_HOST is not a Cloudflare IP.

Blocks `gh variable set VPS_HOST` if the value resolves to a known Cloudflare
IP range. Also warns if a hostname is used instead of a direct IP.

Exit codes:
  0 — allow (not VPS_HOST, or value is a valid direct IP)
  2 — block (value resolves to Cloudflare IP)
"""

import ipaddress
import json
import re
import socket
import sys

# Known Cloudflare IP ranges
CLOUDFLARE_RANGES = [
    ipaddress.ip_network("104.16.0.0/12"),
    ipaddress.ip_network("172.64.0.0/13"),
    ipaddress.ip_network("103.21.244.0/22"),
    ipaddress.ip_network("103.22.200.0/22"),
    ipaddress.ip_network("103.31.4.0/22"),
    ipaddress.ip_network("141.101.64.0/18"),
    ipaddress.ip_network("108.162.192.0/18"),
    ipaddress.ip_network("190.93.240.0/20"),
    ipaddress.ip_network("188.114.96.0/20"),
    ipaddress.ip_network("197.234.240.0/22"),
    ipaddress.ip_network("198.41.128.0/17"),
    ipaddress.ip_network("162.158.0.0/15"),
    ipaddress.ip_network("131.0.72.0/22"),
]


def is_cloudflare_ip(ip_str: str) -> bool:
    """Check if an IP address falls within known Cloudflare ranges."""
    try:
        addr = ipaddress.ip_address(ip_str)
        return any(addr in net for net in CLOUDFLARE_RANGES)
    except ValueError:
        return False


def resolve_hostname(hostname: str) -> str | None:
    """Resolve a hostname to an IP address."""
    try:
        return socket.gethostbyname(hostname)
    except (socket.gaierror, socket.timeout):
        return None


def is_ip_address(value: str) -> bool:
    """Check if a string is a valid IP address."""
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        sys.exit(0)

    command = input_data.get("tool_input", {}).get("command", "")

    # Match gh variable set VPS_HOST <value>
    match = re.search(
        r"\bgh\s+variable\s+set\s+VPS_HOST\s+[\"']?(\S+)[\"']?", command
    )
    if not match:
        sys.exit(0)

    value = match.group(1).strip("\"'")

    # Determine IP to check
    if is_ip_address(value):
        ip_to_check = value
        is_hostname = False
    else:
        is_hostname = True
        ip_to_check = resolve_hostname(value)

    warnings = []

    if is_hostname:
        warnings.append(
            f"WARNING: VPS_HOST is a hostname ({value}), not a direct IP. "
            "SSH should use the direct VPS IP to avoid proxy issues."
        )

    if ip_to_check and is_cloudflare_ip(ip_to_check):
        result = {
            "decision": "block",
            "reason": (
                f"BLOCKED: VPS_HOST value '{value}' resolves to {ip_to_check}, "
                "which is a Cloudflare IP. Cloudflare does not proxy SSH (port 22), "
                "so deploys will fail with connection timeout.\n"
                "Use the direct VPS IP address instead of the proxied domain.\n"
                "Check your hosting provider's dashboard for the origin server IP."
            ),
        }
        print(json.dumps(result))
        sys.exit(2)

    if warnings:
        result = {
            "decision": "allow",
            "systemMessage": "\n".join(warnings),
        }
        print(json.dumps(result))

    sys.exit(0)


if __name__ == "__main__":
    main()
