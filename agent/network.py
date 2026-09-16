from __future__ import annotations

import socket


def addresses() -> list[str]:
    result = []
    for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
        address = item[4][0]
        if not address.startswith("127.") and address not in result:
            result.append(address)
    return result


def primary_address() -> str:
    return addresses()[0] if addresses() else "--"
