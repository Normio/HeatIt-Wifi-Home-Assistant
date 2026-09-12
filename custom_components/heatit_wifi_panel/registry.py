"""The parameter registry: one frozen descriptor per *observed parameter*.

Thirteen parameters, each with its wire name, serialiser, step, bounds, dotted
read path, scale and presence flag (§3.3). The table earns its place four times
over. The write-flat, read-nested mismatch of ``openWindowDetection`` lives
here and nowhere else. The per-parameter step rules have one home. Client-side
validation turns an out-of-range value into a local ``ValueError`` instead of a
device ``400``. And the entities are driven from the same table instead of
restating thirteen ranges.

The two parameters the vendor document lists that no panel has returned
(``externalSensorFallback``, ``lowTemperatureProtection``) are *unobserved* and
left out on purpose. They enter with a captured fixture or not at all.

Values enter this module in **user-facing units**: watts, percent, degrees.
They leave it in the device's own units: ``loadLimit`` in units of 100 W, the
brightnesses in units of 10 %. The scale is applied on the way out (write) and
on the way back (echo and status read). So no value without a unit gets out.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal, NoReturn, Protocol

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

Kind = Literal["int", "float", "bool"]

#: How far a value may sit from its grid point and still count as on it.
#: Caller arithmetic (``0.1 * 3``) lands slightly off the grid; ``19.3`` does
#: not.
GRID_TOLERANCE = 1e-6

#: The panel's own bounds on either *setpoint bank*. They hold whatever the
#: *temperature limits* are narrowed to. The climate entity reports them as its
#: minimum and maximum on a firmware that returns no limits at all. So they are
#: named here, not repeated there.
SETPOINT_MINIMUM = 5.0
SETPOINT_MAXIMUM = 40.0


class StatusDocument(Protocol):
    """Anything that resolves a dotted read path, such as a parsed status."""

    def get(self, path: str) -> object | None:
        """Return the value at ``path``, or ``None`` when it does not resolve."""


def serialise_temperature(value: float) -> str:
    """Already on the grid. One decimal on the wire, as the device echoes it."""
    return f"{value:.1f}"


def serialise_integer(value: float) -> str:
    """Write a bare integer. The device rejects ``5.0`` for an integer one."""
    return str(int(value))


def serialise_boolean(value: float) -> str:
    """Lowercase ``true`` / ``false``. A safety choice, not a bug fix."""
    return "true" if value else "false"


@dataclass(frozen=True, slots=True, kw_only=True)
class ParameterDescriptor:
    """One observed parameter and everything the client needs to handle it."""

    key: str
    """The wire name: the query-string key we send and the echo key we read."""

    kind: Kind
    """The Python type of the value on both sides of the scale."""

    read_path: str
    """The dotted path into the status document where this parameter is read."""

    serialise: Callable[[float], str]
    """Renders the *wire* value, already scaled and validated, for the query."""

    step: float | None = None
    """The grid, in user units, a value must sit on. ``None`` for enums and bools."""

    minimum: float | None = None
    """Inclusive lower bound, in user units."""

    maximum: float | None = None
    """Inclusive upper bound, in user units."""

    choices: tuple[int, ...] | None = None
    """The closed set of values for an enumerated parameter."""

    scale: int = 1
    """User value = wire value times scale. ``100`` for the load limit, ``10``
    for the brightnesses, ``1`` everywhere else."""

    required: bool = False
    """Part of the *required core*: a status without it is not a status. Every
    other parameter is optional. A firmware that stops returning one must not
    break setup, and its absence leaves only its own reading unknown."""

    def encode(self, value: object) -> str:
        """Validate a user-facing value and render it for the wire.

        Raises ``ValueError`` locally, before any request exists. That covers
        a value of the wrong type, off the grid, outside the bounds or not
        among the choices. The message names the parameter.
        """
        return self.serialise(self.to_wire(value))

    def decode(self, echo: object) -> int | float | bool | None:
        """Convert an echoed (or read) wire value to the declared type and scale.

        The device changes types: ``19`` for ``19.0``, ``-1`` for ``-1.0``. So
        a numeric echo is converted, not compared. Anything the declared type
        cannot take decodes to ``None``, and the caller falls back to the value
        it requested.
        """
        if self.kind == "bool":
            return echo if isinstance(echo, bool) else None
        if isinstance(echo, bool) or not isinstance(echo, int | float):
            return None
        if self.kind == "int":
            return echo * self.scale if isinstance(echo, int) else None
        return float(echo) * self.scale

    def read(self, status: StatusDocument) -> int | float | bool | None:
        """Read the parameter's current value from a status, in user units."""
        return self.decode(status.get(self.read_path))

    def present_in(self, status: StatusDocument) -> bool:
        """Whether the read path resolves: the presence flag at runtime."""
        return status.get(self.read_path) is not None

    def to_wire(self, value: object) -> int | float | bool:
        """Validate a user-facing value and scale it into the device's unit.

        The checked half of :meth:`encode`. ``decode`` of the result is the
        value as the device will hold it. A caller falls back to that when the
        echo is missing.
        """
        if self.kind == "bool":
            if not isinstance(value, bool):
                self._reject(value, "must be a boolean")
            return value
        if isinstance(value, bool) or not isinstance(value, int | float):
            self._reject(value, "must be a number")
        if self.choices is not None:
            if value not in self.choices:
                self._reject(value, f"must be one of {list(self.choices)}")
            return int(value)
        wire = self._on_grid_and_in_bounds(value) / self.scale
        # An integer parameter's step is its scale, so an on-grid value is a
        # whole number on the wire. The registry test checks that this always
        # holds.
        return wire if self.kind == "float" else round(wire)

    def _on_grid_and_in_bounds(self, value: float) -> float:
        checked = value
        if self.step is not None:
            checked = round(round(value / self.step) * self.step, 6)
            if abs(value - checked) > GRID_TOLERANCE:
                self._reject(value, f"must be a multiple of {self.step}")
        if self.minimum is not None and checked < self.minimum:
            self._reject(value, f"is below the minimum of {self.minimum}")
        if self.maximum is not None and checked > self.maximum:
            self._reject(value, f"is above the maximum of {self.maximum}")
        return checked

    def _reject(self, value: object, why: str) -> NoReturn:
        msg = f"{self.key}={value!r} {why}"
        raise ValueError(msg)


def _temperature(key: str, *, required: bool = False) -> ParameterDescriptor:
    return ParameterDescriptor(
        key=key,
        kind="float",
        read_path=f"parameters.{key}",
        serialise=serialise_temperature,
        step=0.5,
        minimum=SETPOINT_MINIMUM,
        maximum=SETPOINT_MAXIMUM,
        required=required,
    )


OBSERVED_PARAMETERS: tuple[ParameterDescriptor, ...] = (
    ParameterDescriptor(
        key="panelMode",
        kind="int",
        read_path="parameters.panelMode",
        serialise=serialise_integer,
        choices=(0, 1, 2),
        required=True,
    ),
    _temperature("heatingSetpoint", required=True),
    _temperature("ecoSetpoint", required=True),
    _temperature("minimumTemperatureLimit"),
    _temperature("maximumTemperatureLimit"),
    ParameterDescriptor(
        key="sensorCalibration",
        kind="float",
        read_path="parameters.sensorCalibration",
        serialise=serialise_temperature,
        step=0.1,
        minimum=-6.0,
        maximum=6.0,
    ),
    ParameterDescriptor(
        key="loadLimit",
        kind="int",
        read_path="parameters.loadLimit",
        serialise=serialise_integer,
        step=100,
        minimum=100,
        maximum=1500,
        scale=100,
    ),
    ParameterDescriptor(
        key="activeDisplayBrightness",
        kind="int",
        read_path="parameters.activeDisplayBrightness",
        serialise=serialise_integer,
        step=10,
        minimum=10,
        maximum=100,
        scale=10,
    ),
    ParameterDescriptor(
        key="standbyDisplayBrightness",
        kind="int",
        read_path="parameters.standbyDisplayBrightness",
        serialise=serialise_integer,
        step=10,
        minimum=0,
        maximum=100,
        scale=10,
    ),
    ParameterDescriptor(
        key="disableButtons",
        kind="int",
        read_path="parameters.disableButtons",
        serialise=serialise_integer,
        choices=(0, 1, 2),
    ),
    ParameterDescriptor(
        key="temperatureDisplay",
        kind="bool",
        read_path="parameters.temperatureDisplay",
        serialise=serialise_boolean,
    ),
    ParameterDescriptor(
        key="sensorMode",
        kind="bool",
        read_path="parameters.sensorMode",
        serialise=serialise_boolean,
    ),
    # Written flat, read nested: the one mismatch, hard-coded here only.
    ParameterDescriptor(
        key="openWindowDetection",
        kind="bool",
        read_path="parameters.OWD.openWindowDetection",
        serialise=serialise_boolean,
    ),
)

PARAMETERS: Mapping[str, ParameterDescriptor] = MappingProxyType(
    {descriptor.key: descriptor for descriptor in OBSERVED_PARAMETERS}
)
"""The registry, keyed by wire name."""
