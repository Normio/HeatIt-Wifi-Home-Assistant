"""The device client: the Heatit WiFi Panel over its local HTTP API (§3.2).

Imports nothing from ``homeassistant``. Not for portability — there is no
library — but for testability: the client is exercised over ``aioresponses``
with no ``hass``, and ``scripts/capture_fixtures.py`` imports it directly
without booting Home Assistant.

Public surface, exactly four methods: :meth:`HeatitClient.get_status` (the only
one with a retry), :meth:`HeatitClient.set_parameter`,
:meth:`HeatitClient.reset_kwh` and :meth:`HeatitClient.reset_settings`. There
is deliberately no request method taking a retry count, so a retried reset
cannot be written by accident.

Alongside the client: the *status* parser and the one redaction function
shared by logging, diagnostics and fixture capture (§7.1).
"""

from __future__ import annotations

import asyncio
import json
import re
import string
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

import aiohttp

from .const import (
    CONNECT_TIMEOUT_SECONDS,
    LOGGER,
    STATUS_ATTEMPTS,
    STATUS_TIMEOUT_SECONDS,
    WRITE_TIMEOUT_SECONDS,
)
from .registry import PARAMETERS

if TYPE_CHECKING:
    from collections.abc import Mapping

STATUS_PATH: Final = "/api/status"
PARAMETERS_PATH: Final = "/api/parameters"
RESET_KWH_PATH: Final = "/api/reset/kwh"
RESET_SETTINGS_PATH: Final = "/api/reset/settings"

#: The enum is not enforced at firmware 1.21 — provably ignored — and sending
#: it matches the documented contract, so it is free insurance (§2.5).
RESET_KWH_QUERY: Final = {"resetKwh": "Reset"}

HTTP_OK: Final = 200
HTTP_BAD_REQUEST: Final = 400

STATUS_TIMEOUT: Final = aiohttp.ClientTimeout(
    total=STATUS_TIMEOUT_SECONDS, connect=CONNECT_TIMEOUT_SECONDS
)
WRITE_TIMEOUT: Final = aiohttp.ClientTimeout(
    total=WRITE_TIMEOUT_SECONDS, connect=CONNECT_TIMEOUT_SECONDS
)

#: The *required core*: a status missing any of these is not a status. The
#: three parameters are the registry's ``required`` descriptors.
REQUIRED_CORE: Final[tuple[str, ...]] = (
    "id",
    "state",
    "roomTemperature",
    *(d.read_path for d in PARAMETERS.values() if d.required),
)

#: Exactly the fields the shared redaction scrubs, and the fixed,
#: shape-preserving placeholder each becomes (§7.1, §8.3). ``name`` and ``room``
#: are kept: they are human labels, not identifiers, and ``name`` is the
#: evidence that the charset-less UTF-8 decode is required.
REDACTED_FIELDS: Final[Mapping[str, str]] = {
    "id": "FIXTUREFIXTUREFIXTUREX",  # 22 chars, mixed case, like a real id
    "Network.mac": "02:00:00:00:00:01",  # locally administered, format_mac ok
    "Network.SSID": "SSID-REDACTED",
    "Network.ipAddress": "10.0.0.2",  # RFC 1918
}

WIFI_SIGNAL_STRENGTH: Final = "Network.wifiSignalStrength"
"""Where the signal strength sits in a *status*.

Named because two modules need the same path and must not drift: the
:attr:`PanelStatus.signal_strength_dbm` parse below, and the read path the
diagnostic sensor's presence and availability are gated on (§5.2).
"""

TOTAL_CONSUMPTION: Final = "totalConsumption"
"""Where the *energy counter* sits in a *status*.

Named for the same reason as :data:`WIFI_SIGNAL_STRENGTH`: two modules read the
same path and must not drift. The energy sensor publishes it, and the
coordinator reads it twice more — once as the pre-reset value a press records,
once as the reading a later poll judges that press by (§5.5).
"""

SIGNAL_STRENGTH: Final = re.compile(r"^\s*(-?\d+)\s*dBm\s*$", re.IGNORECASE)


# --- exceptions (device vocabulary, no Home Assistant types) -----------------


class HeatitError(Exception):
    """Base of every error the client raises."""


class HeatitConnectionError(HeatitError):
    """Timeout, refused, dropped, or an OS-level failure."""


class HeatitResponseError(HeatitError):
    """An unexpected HTTP status, or a ``failed`` envelope on a reset.

    Carries the status code and the device's ``reason`` verbatim — never
    parsed, never branched on. When the body carries no ``reason`` the HTTP
    reason phrase stands in, so raw response bytes never reach a log line.
    """

    def __init__(
        self, status_code: int, reason: str, message: str | None = None
    ) -> None:
        """Record the code and the device's own words."""
        super().__init__(message or f"HTTP {status_code}: {reason}")
        self.status_code = status_code
        self.reason = reason


class HeatitParameterRejected(HeatitResponseError):  # noqa: N818 - the spec names it
    """The device refused a parameter write: a ``400``, or a ``failed`` 200.

    Additionally carries the parameter name **we sent**, because ``reason``
    cannot be parsed for it.
    """

    def __init__(self, parameter: str, status_code: int, reason: str) -> None:
        """Record which of our parameters the device refused, and why."""
        super().__init__(
            status_code, reason, f"{parameter} rejected by the panel: {reason}"
        )
        self.parameter = parameter


class HeatitProtocolError(HeatitError):
    """A 200 whose body we could not make sense of.

    The message carries content type, byte length and the underlying error —
    never the bytes (§7.1).
    """


class HeatitMissingFieldError(HeatitProtocolError):
    """A status that parses but lacks a *required core* field, or holds ``null``."""

    def __init__(self, path: str) -> None:
        """Name the dotted path that did not resolve."""
        super().__init__(f"status is missing {path}")
        self.path = path


# --- the status -------------------------------------------------------------


def resolve(document: Mapping[str, Any], path: str) -> object | None:
    """Walk a dotted path; ``None`` when it does not resolve or holds ``null``.

    No status field has ever been ``null`` (Q24), so ``null`` is treated exactly
    as absent and the integration models no third state.
    """
    node: object = document
    for segment in path.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(segment)
    return node


def parse_signal_strength(value: object) -> int | None:
    """``"-67dBm"`` → ``-67``. No sign fix-up; garbage → ``None``, no exception."""
    match = SIGNAL_STRENGTH.match(value) if isinstance(value, str) else None
    if match is None:
        LOGGER.debug("wifiSignalStrength %r is not of the form -NNdBm", value)
        return None
    return int(match.group(1))


@dataclass(frozen=True, slots=True)
class PanelStatus:
    """The panel's complete state, parsed from one ``GET /api/status``.

    The *required core* is typed and guaranteed present. Everything else is
    read through :meth:`get` and its typed variants, which answer ``None`` for
    a field this firmware did not return — absent means that reading alone is
    unknown. Unknown keys are kept in :attr:`document` and otherwise ignored.
    """

    device_id: str
    """The panel's own identifier — 22 mixed-case alphanumerics, verbatim."""

    relay_state: str
    """The *relay state*, wire name ``state``: ``Idle`` or ``Heating``."""

    room_temperature: float
    panel_mode: int
    comfort_setpoint: float
    """The *comfort setpoint*, wire name ``heatingSetpoint``."""
    eco_setpoint: float

    document: Mapping[str, Any]
    """The whole parsed status, unknown keys included."""

    def get(self, path: str) -> object | None:
        """Resolve a dotted read path, treating ``null`` as absent."""
        return resolve(self.document, path)

    def get_str(self, path: str) -> str | None:
        """Return the string at ``path``, or ``None`` when absent or not one."""
        value = self.get(path)
        return value if isinstance(value, str) else None

    def get_float(self, path: str) -> float | None:
        """Return the number at ``path`` as a float, or ``None``."""
        value = self.get(path)
        if isinstance(value, bool) or not isinstance(value, int | float):
            return None
        return float(value)

    def get_int(self, path: str) -> int | None:
        """Return the integer at ``path``, or ``None``; a bool is not one."""
        value = self.get(path)
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    def get_bool(self, path: str) -> bool | None:
        """Return the boolean at ``path``, or ``None``."""
        value = self.get(path)
        return value if isinstance(value, bool) else None

    @property
    def name(self) -> str | None:
        """The MyHeatit app's device name; free text, non-ASCII in the wild."""
        return self.get_str("name")

    @property
    def room(self) -> str | None:
        """The *assigned room*: ``""`` when none is assigned."""
        return self.get_str("room")

    @property
    def model(self) -> str | None:
        """Undocumented, present because we looked; never a fingerprint."""
        return self.get_str("model")

    @property
    def firmware(self) -> str | None:
        """The firmware version; absent means unverified, not an error."""
        return self.get_str("firmware")

    @property
    def mac(self) -> str | None:
        """``Network.mac`` as received: uppercase with colons."""
        return self.get_str("Network.mac")

    @property
    def signal_strength_dbm(self) -> int | None:
        """``Network.wifiSignalStrength`` parsed, or ``None``."""
        return parse_signal_strength(self.get(WIFI_SIGNAL_STRENGTH))


def _decode_json(raw: bytes, content_type: str) -> object:
    """Bytes → UTF-8 explicitly → JSON. Never ``response.json()``.

    Success carries no ``charset`` and real non-ASCII; error paths serve
    ``text/html``. Either failure is a :class:`HeatitProtocolError` naming the
    content type and byte length, never the bytes.
    """
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        msg = f"could not parse a {content_type!r} response of {len(raw)} bytes: {err}"
        raise HeatitProtocolError(msg) from err


def parse_status(raw: bytes, content_type: str = "application/json") -> PanelStatus:
    """Parse the bytes of ``GET /api/status`` into a :class:`PanelStatus`.

    Raises :class:`HeatitMissingFieldError` for an absent or ``null``
    *required core* field and :class:`HeatitProtocolError` for a body that is
    not a JSON object or holds a required field of the wrong type.
    """
    document = _decode_json(raw, content_type)
    if not isinstance(document, dict):
        msg = f"status is {type(document).__name__}, not a JSON object"
        raise HeatitProtocolError(msg)
    for path in REQUIRED_CORE:
        if resolve(document, path) is None:
            raise HeatitMissingFieldError(path)
    return PanelStatus(
        device_id=_required_str(document, "id"),
        relay_state=_required_str(document, "state"),
        room_temperature=_required_float(document, "roomTemperature"),
        panel_mode=_required_int(document, PARAMETERS["panelMode"].read_path),
        comfort_setpoint=_required_float(
            document, PARAMETERS["heatingSetpoint"].read_path
        ),
        eco_setpoint=_required_float(document, PARAMETERS["ecoSetpoint"].read_path),
        document=document,
    )


def _wrong_type(path: str, value: object, expected: str) -> HeatitProtocolError:
    return HeatitProtocolError(
        f"status field {path} is {type(value).__name__}, not {expected}"
    )


def _required_str(document: Mapping[str, Any], path: str) -> str:
    value = resolve(document, path)
    if not isinstance(value, str):
        raise _wrong_type(path, value, "a string")
    return value


def _required_int(document: Mapping[str, Any], path: str) -> int:
    value = resolve(document, path)
    if isinstance(value, bool) or not isinstance(value, int):
        raise _wrong_type(path, value, "an integer")
    return value


def _required_float(document: Mapping[str, Any], path: str) -> float:
    value = resolve(document, path)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise _wrong_type(path, value, "a number")
    return float(value)


# --- the one redaction ------------------------------------------------------


def redact_status(document: Mapping[str, Any]) -> dict[str, Any]:
    """Copy a parsed status with exactly the four identifiers replaced.

    Shared by logging and diagnostics; :func:`redact_status_bytes` is the same
    scrub at the wire level, for the raw section and fixture capture.
    """
    redacted: dict[str, Any] = dict(document)
    for path, placeholder in REDACTED_FIELDS.items():
        *parents, key = path.split(".")
        node = redacted
        for parent in parents:
            child = node.get(parent)
            if not isinstance(child, dict):
                break
            node[parent] = child = dict(child)
            node = child
        else:
            if key in node:
                node[key] = placeholder
    return redacted


def substitute_string_field(raw: bytes, key: str, placeholder: str) -> bytes:
    """Replace the string value of every ``"key"`` in raw JSON bytes, in place.

    Only the quoted value moves; spacing, ordering and every other byte stay
    as the device sent them, so ``0.00`` stays ``0.00``.
    """
    pattern = rb'("' + re.escape(key.encode()) + rb'"\s*:\s*)"(?:[^"\\]|\\.)*"'
    return re.sub(pattern, rb'\1"' + placeholder.encode() + b'"', raw)


def redact_text(text: str, document: Mapping[str, Any]) -> str:
    """Replace this panel's own identifiers wherever they occur in free text.

    The third face of the one redaction, for text that is neither a parsed
    status nor a JSON body: a response header. The fields and placeholders are
    :data:`REDACTED_FIELDS`, but the value to look for is read from the status
    the panel just returned, because a header does not name its contents.

    Substring matching, so it can only ever over-scrub — which at the wire is
    the documented direction (:func:`redact_status_bytes`).
    """
    for path, placeholder in REDACTED_FIELDS.items():
        value = resolve(document, path)
        if isinstance(value, str) and value:
            text = text.replace(value, placeholder)
    return text


def redact_status_bytes(raw: bytes) -> bytes:
    """Apply the same scrub to the raw bytes, by targeted substitution.

    At the wire level a field is found by its key wherever it appears, not by
    its path — a superset that can only ever over-scrub. On a real status the
    two agree, and a test asserts that :func:`redact_status` of the parsed
    document equals the parse of these bytes.
    """
    for path, placeholder in REDACTED_FIELDS.items():
        raw = substitute_string_field(raw, path.rsplit(".", 1)[-1], placeholder)
    return raw


# --- the client -------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Response:
    status: int
    reason: str
    content_type: str
    headers: dict[str, str]
    body: bytes


def _is_success(status: str) -> bool:
    """Case-insensitive after stripping whitespace and trailing punctuation.

    Mandatory, not defensive: the device ships ``"Success"`` capitalised and
    ``"failed"`` lowercase, contradicting the document and itself.
    """
    return status.strip().rstrip(string.punctuation).strip().casefold() == "success"


class HeatitClient:
    """One panel at one host, over a session the caller owns.

    Every request to the panel — poll, write, reset — waits its turn on one
    ``asyncio.Lock``, so a single Home Assistant instance never presents a
    panel with more than one connection and write-then-refresh order is
    guaranteed rather than left to the device. Lock wait is outside the
    timeout budget: timeouts cover wire time only.
    """

    def __init__(self, host: str, *, session: aiohttp.ClientSession) -> None:
        """Bind to ``host`` (plain HTTP on tcp/80) and a session never created here."""
        self._host = host
        self._base_url = f"http://{host}"
        self._session = session
        self._lock = asyncio.Lock()
        self.last_raw_body: bytes | None = None
        """The last status response body as received, for diagnostics (§7.3)."""
        self.last_raw_headers: Mapping[str, str] | None = None
        """The last status response headers as received."""
        self.last_status_retried = False
        """Whether the last status read used its retry, successfully or not.

        Set when the second attempt is *made*, so the diagnostics download of
        §7.3 answers "did the retry fire?" for a poll that failed as well as
        for one that recovered.
        """

    async def get_status(self) -> PanelStatus:
        """Read the whole *status*: the only read, and the only retried request.

        Retried once on any transport failure, no backoff, within the *poll
        budget*. Raises :class:`HeatitConnectionError` when both attempts
        fail, :class:`HeatitResponseError` for a non-200, and
        :class:`HeatitProtocolError` for a 200 that is not a status.
        """
        async with self._lock:
            response = await self._fetch_status()
        if response.status != HTTP_OK:
            raise HeatitResponseError(response.status, self._reason_of(response))
        self.last_raw_body = response.body
        self.last_raw_headers = response.headers
        status = parse_status(response.body, response.content_type)
        LOGGER.debug(
            "GET %s -> %d, %d bytes: %s",
            STATUS_PATH,
            response.status,
            len(response.body),
            redact_status(status.document),
        )
        return status

    async def set_parameter(self, key: str, value: object) -> object:
        """Write one *observed parameter* and return the value applied.

        ``value`` is in user-facing units; the registry validates it locally —
        a ``ValueError`` here means no request was sent — and scales it for
        the wire. The return value is the device's *write echo* coerced to the
        declared type, or the requested value when the echo is missing or
        unparseable. One attempt, never retried.
        """
        descriptor = PARAMETERS.get(key)
        if descriptor is None:
            msg = f"{key} is not an observed parameter"
            raise ValueError(msg)
        wire_value = descriptor.to_wire(value)
        wire = descriptor.serialise(wire_value)
        requested = descriptor.decode(wire_value)
        async with self._lock:
            response = await self._fetch(
                "POST", PARAMETERS_PATH, params={key: wire}, budget=WRITE_TIMEOUT
            )
        envelope = self._verdict(response, parameter=key)
        echo = envelope.get(key)
        applied = descriptor.decode(echo)
        LOGGER.debug(
            "POST %s?%s=%s -> %d, echoed %r",
            PARAMETERS_PATH,
            key,
            wire,
            response.status,
            echo,
        )
        return requested if applied is None else applied

    async def reset_kwh(self) -> None:
        """Zero the *energy counter*. One attempt, never retried."""
        await self._reset(RESET_KWH_PATH, params=RESET_KWH_QUERY)

    async def reset_settings(self) -> None:
        """Parameters to defaults; keeps network, pairing, id, name and room.

        Applies staggered over about 5 s on the device. One attempt, never
        retried.
        """
        await self._reset(RESET_SETTINGS_PATH, params=None)

    async def _reset(self, path: str, *, params: Mapping[str, str] | None) -> None:
        async with self._lock:
            response = await self._fetch(
                "DELETE", path, params=params, budget=WRITE_TIMEOUT
            )
        self._verdict(response, parameter=None)
        LOGGER.debug("DELETE %s -> %d", path, response.status)

    async def _fetch_status(self) -> _Response:
        """Two attempts at the status, the second only after a transport failure."""
        self.last_status_retried = False
        first_error: HeatitConnectionError | None = None
        for attempt in range(1, STATUS_ATTEMPTS + 1):
            try:
                response = await self._fetch("GET", STATUS_PATH, budget=STATUS_TIMEOUT)
            except HeatitConnectionError as err:
                if attempt == STATUS_ATTEMPTS:
                    raise
                first_error = err
                self.last_status_retried = True
                continue
            if first_error is not None:
                LOGGER.debug(
                    "status read of %s succeeded on retry; first attempt: %s",
                    self._host,
                    first_error,
                )
            return response
        raise AssertionError  # pragma: no cover - the loop returns or raises

    async def _fetch(
        self,
        method: str,
        path: str,
        *,
        budget: aiohttp.ClientTimeout,
        params: Mapping[str, str] | None = None,
    ) -> _Response:
        """One HTTP exchange; the body is read as bytes, never decoded here."""
        try:
            async with self._session.request(
                method, f"{self._base_url}{path}", params=params, timeout=budget
            ) as response:
                body = await response.read()
                return _Response(
                    status=response.status,
                    reason=response.reason or "",
                    content_type=response.headers.get("Content-Type", ""),
                    headers=dict(response.headers),
                    body=body,
                )
        except (aiohttp.ClientError, TimeoutError) as err:
            msg = f"{method} {path} failed: {err!r}"
            raise HeatitConnectionError(msg) from err

    def _verdict(self, response: _Response, *, parameter: str | None) -> dict[str, Any]:
        """HTTP 200 **and** ``status`` matched, one envelope for the whole API."""
        if response.status != HTTP_OK:
            reason = self._reason_of(response)
            if parameter is not None and response.status == HTTP_BAD_REQUEST:
                raise HeatitParameterRejected(parameter, response.status, reason)
            raise HeatitResponseError(response.status, reason)
        envelope = _decode_json(response.body, response.content_type)
        if not isinstance(envelope, dict) or not isinstance(
            envelope.get("status"), str
        ):
            msg = (
                f"a {response.content_type!r} 200 of {len(response.body)} bytes "
                f"carries no status envelope"
            )
            raise HeatitProtocolError(msg)
        if not _is_success(envelope["status"]):
            device_reason = envelope.get("reason")
            reason = (
                device_reason
                if isinstance(device_reason, str)
                else str(envelope["status"])
            )
            if parameter is not None:
                raise HeatitParameterRejected(parameter, response.status, reason)
            raise HeatitResponseError(response.status, reason)
        return envelope

    @staticmethod
    def _reason_of(response: _Response) -> str:
        """Return the device's ``reason``, else the HTTP reason phrase.

        A ``text/html`` body therefore never becomes a message.
        """
        try:
            envelope = _decode_json(response.body, response.content_type)
        except HeatitProtocolError:
            return response.reason
        if isinstance(envelope, dict) and isinstance(envelope.get("reason"), str):
            return str(envelope["reason"])
        return response.reason
