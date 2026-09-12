"""Builders for synthesised fixtures, derived from observed bytes (§8.3).

A synthesised status is made by parsing the reference bytes, changing the
named paths and encoding again. Every part that was not changed is real.
Nobody is going to turn on a bedroom heater to capture off mode, a dropped
parameter, an unknown key or a ``null``, so those cases are made this way.
No synthesised fixture may add a field that no observed fixture holds.

This module also holds :class:`FakeHeatitClient`, the seam where the config
flow, the coordinator and the entities are tested (§8.4). It is built from
observed bytes and parses them with the **real** parser, so its status shape
cannot drift from what the client produces.
"""

import json
from collections import deque
from typing import TYPE_CHECKING, Any

from custom_components.heatit_wifi_panel.api import (
    PanelStatus,
    parse_status,
    substitute_string_field,
)
from custom_components.heatit_wifi_panel.registry import PARAMETERS
from tests.conftest import SYNTHESISED_DIR

if TYPE_CHECKING:
    from collections.abc import Mapping

ABSENT = object()
"""Set a path to this to drop it from the synthesised status."""

UNSCRUBBED: dict[str, str] = {
    "id": "AbCdEfGhIjKlMnOpQrStUv",
    "Network.mac": "E4:B3:23:AA:BB:CC",
    "Network.SSID": "Example IoT 2.4",
    "Network.ipAddress": "192.0.2.40",
}
"""The four scrubbed fields, in the *shape* a real panel answers them in.

Every committed fixture carries the placeholders, so a test of the redaction
has to put something unscrubbed back first (§7.1). The client's scrub tests
and the diagnostics rule test share this because they mean the same panel.

**Every value here is invented, and must stay invented.** The tests only
need the shape: 22 letters and digits in mixed case, an uppercase MAC with
colons, an SSID with a space in it, a dotted address. The OUI is Espressif's
because that is a fact about the hardware (§2.3) and costs nothing to keep.
The rest of the MAC belongs to no device. The address is RFC 5737 TEST-NET-1,
which is reserved for documentation and routes nowhere. AGENTS.md says never
hardcode a panel's address and never commit one. The real one lives in
`.local/device.json`, which is gitignored for this reason. A test that needs
a believable address must not read it.
"""


def mutated(raw: bytes, changes: Mapping[str, object]) -> bytes:
    """Derive a status from observed bytes by setting or dropping dotted paths.

    A missing intermediate object is created, so a nested key can be added.
    Only the *unknown keys are ignored* test uses that.
    """
    document: dict[str, Any] = json.loads(raw.decode("utf-8"))
    for path, value in changes.items():
        *parents, key = path.split(".")
        node = document
        for parent in parents:
            node = node.setdefault(parent, {})
        if value is ABSENT:
            node.pop(key, None)
        else:
            node[key] = value
    return json.dumps(document, ensure_ascii=False).encode("utf-8")


def unscrubbed(raw: bytes) -> bytes:
    """Put a real panel's four identifiers back into a committed fixture.

    This is the inverse of the shared wire-level scrub, done the same way. Only
    the quoted values change, so ``0.00`` stays ``0.00`` and the result is what
    the panel sent, byte for byte. :func:`mutated` cannot do this because it
    encodes again through ``json.dumps``. And a test that scrubs a fixture
    that is already scrubbed proves only that nothing was damaged.
    """
    for path, real in UNSCRUBBED.items():
        raw = substitute_string_field(raw, path.rsplit(".", 1)[-1], real)
    return raw


def synthesised(name: str) -> bytes:
    """Load a transcribed write-path response from ``fixtures/synthesised/``."""
    return (SYNTHESISED_DIR / name).read_bytes()


def synthesised_manifest() -> dict[str, dict[str, Any]]:
    """Load what each synthesised file is, and what it was transcribed from."""
    manifest = json.loads((SYNTHESISED_DIR / "manifest.json").read_text("utf-8"))
    files: dict[str, dict[str, Any]] = manifest["files"]
    return files


class FakeHeatitClient:
    """The real client's four methods over observed bytes, plus a record of calls.

    Reads answer from :attr:`raw`, parsed by the real parser. Writes are
    recorded and echoed the way the device echoes them: the *applied* value,
    with its type normalised. So an optimistic update is tested against real
    behaviour. Failures are scripted, not simulated: :meth:`fail` queues the
    exceptions the next reads raise, and :meth:`set_status` changes the status
    a later poll returns.
    """

    def __init__(self, raw: bytes, headers: Mapping[str, str] | None = None) -> None:
        """Answer reads from ``raw`` until a test says otherwise."""
        self.raw = raw
        self.headers = dict(headers or {})
        self.last_raw_body: bytes | None = None
        self.last_raw_headers: Mapping[str, str] | None = None
        self.retries = False
        """Set this to make reads report that the status took the retry (§3.6)."""
        self.last_status_retried = False
        self.status_reads = 0
        self.writes: list[tuple[str, object]] = []
        self.resets: list[str] = []
        self.echoes: dict[str, object] = {}
        """Force a *write echo* for one parameter: the *silent undo* case."""
        self._failures: deque[Exception] = deque()
        self._refusals: deque[Exception] = deque()
        self._reset_refusals: deque[Exception] = deque()

    def fail(self, error: Exception, times: int = 1) -> None:
        """Queue ``error`` for the next ``times`` status reads."""
        self._failures.extend([error] * times)

    def refuse(self, error: Exception, times: int = 1) -> None:
        """Queue ``error`` for the next ``times`` parameter writes."""
        self._refusals.extend([error] * times)

    def refuse_reset(self, error: Exception, times: int = 1) -> None:
        """Queue ``error`` for the next ``times`` resets, either kind."""
        self._reset_refusals.extend([error] * times)

    def set_status(self, changes: Mapping[str, object]) -> None:
        """Derive the status later reads return, by dotted path (:func:`mutated`)."""
        self.raw = mutated(self.raw, changes)

    async def get_status(self) -> PanelStatus:
        """Read the whole status, or raise the next scripted failure.

        The raw body and headers are kept the way the real client keeps them:
        set before the parse, and untouched by a read that failed. The retry
        flag is decided per read, the way the real client decides it, instead
        of staying wherever a test last put it.
        """
        self.status_reads += 1
        self.last_status_retried = self.retries
        if self._failures:
            raise self._failures.popleft()
        self.last_raw_body = self.raw
        self.last_raw_headers = self.headers
        return parse_status(self.raw)

    async def set_parameter(self, key: str, value: object) -> object:
        """Record the write and echo what the device would have applied."""
        if self._refusals:
            raise self._refusals.popleft()
        descriptor = PARAMETERS[key]
        wire_value = descriptor.to_wire(value)
        self.writes.append((key, descriptor.serialise(wire_value)))
        if key in self.echoes:
            return self.echoes[key]
        return descriptor.decode(wire_value)

    async def reset_kwh(self) -> None:
        """Record an *energy counter* reset, or raise the next scripted refusal."""
        self._reset("kwh")

    async def reset_settings(self) -> None:
        """Record a settings reset, with the same refusal rule."""
        self._reset("settings")

    def _reset(self, kind: str) -> None:
        if self._reset_refusals:
            raise self._reset_refusals.popleft()
        self.resets.append(kind)
