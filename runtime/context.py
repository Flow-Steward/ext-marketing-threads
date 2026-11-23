"""One invocation's ports: its input and its Threads transport."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from .connection import Connection
from .transport import ThreadsTransport

TransportFactory = Callable[[Connection], ThreadsTransport]


class Context:
    """One invocation: its input and its connection's transport."""

    def __init__(
        self,
        *,
        payload: Mapping[str, Any],
        operation_input: Mapping[str, Any],
        transport: ThreadsTransport,
    ) -> None:
        self.payload = payload
        self.operation_input = operation_input
        self.transport = transport

    @property
    def connection(self) -> Connection:
        return self.transport.connection
