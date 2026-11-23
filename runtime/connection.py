"""Project-scoped Threads connection: one Threads account and its user access token.

A Threads user access token comes from Meta's own authorization flow and is
entered in the connection form; Flow Steward keeps it as an encrypted connection
secret and gives a step only ``target.connection.secrets.access_token``. This
extension never exchanges, refreshes or stores a token: Threads issues a
short-lived token (one hour) at the code exchange and makes it long-lived (60 days)
or refreshes it only through its own ``th_exchange_token`` / ``th_refresh_token``
requests, which the Flow Steward OAuth mechanism does not perform. A token that
expired is replaced in the connection form, as with Flow Steward's Instagram
extension.

The token lives in a private field of a frozen dataclass whose ``repr`` never shows
it; it travels only in the ``Authorization`` header and is never placed in a
result, a log line or an exception message.
"""

from __future__ import annotations

import html
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote, quote_plus

from . import errors
from .errors import ExtensionError

CONNECTION_TYPE = "threads_account"
API_HOST = "graph.threads.com"
API_VERSION = "v1.0"
SECRET_FIELDS: frozenset[str] = frozenset({"access_token"})
#: Shorter tokens could not be removed from answers without mangling them.
MIN_TOKEN_LENGTH = 16
MAX_TOKEN_LENGTH = 4096
#: Printable ASCII without spaces: a header value that cannot be split.
_TOKEN_RE = re.compile(r"^[\x21-\x7e]+$")


@dataclass(frozen=True)
class Connection:
    """One validated Threads connection."""

    connection_id: str
    _access_token: str = field(repr=False)

    @property
    def access_token(self) -> str:
        return self._access_token

    @property
    def base_url(self) -> str:
        return f"https://{API_HOST}/{API_VERSION}"

    def secret_forms(self) -> tuple[str, ...]:
        """Every way the token can appear in a text: as is and encoded."""
        token = self._access_token
        forms = {
            token,
            quote_plus(token, safe=""),
            quote(token, safe=""),
            json.dumps(token, ensure_ascii=False)[1:-1],
            html.escape(token, quote=True),
            html.escape(token, quote=False),
        }
        # Longest first, so a form that contains another is removed whole.
        return tuple(sorted((f for f in forms if f), key=len, reverse=True))

    def __repr__(self) -> str:  # pragma: no cover - defensive
        return f"Connection(connection_id={self.connection_id!r})"

    __str__ = __repr__


def _invalid(message: str) -> ExtensionError:
    return errors.no_effect(errors.INVALID_CONNECTION, message)


def _token(value: Any) -> str:
    text = value.strip() if isinstance(value, str) else ""
    if not text:
        raise _invalid(
            "The connection has no Threads access token; enter one in the connection form"
        )
    if (
        len(text) < MIN_TOKEN_LENGTH
        or len(text) > MAX_TOKEN_LENGTH
        or not _TOKEN_RE.fullmatch(text)
    ):
        raise _invalid("The connection holds an unusable Threads access token; enter it again")
    return text


def connection_from_payload(payload: Mapping[str, Any], *, connection_ref: str) -> Connection:
    """Validate the selected project connection before any outbound request."""
    action = payload.get("action")
    target = action.get("target") if isinstance(action, Mapping) else None
    connection = target.get("connection") if isinstance(target, Mapping) else None
    if not isinstance(connection, Mapping):
        raise _invalid("The selected connection is unavailable")
    connection_id = str(connection.get("connection_id") or "")
    if not connection_id or (connection_ref and connection_id != connection_ref):
        raise _invalid("The selected connection does not match connection_ref")
    connection_type = str(
        connection.get("connection_type_id") or connection.get("connection_type") or ""
    )
    if connection_type != CONNECTION_TYPE:
        raise _invalid("The selected connection is not a Threads connection")
    secrets = connection.get("secrets")
    secrets = secrets if isinstance(secrets, Mapping) else {}
    if set(secrets) - SECRET_FIELDS:
        raise _invalid("The connection carries unsupported secrets")
    return Connection(
        connection_id=connection_id, _access_token=_token(secrets.get("access_token"))
    )


__all__ = ["API_HOST", "API_VERSION", "CONNECTION_TYPE", "Connection", "connection_from_payload"]
