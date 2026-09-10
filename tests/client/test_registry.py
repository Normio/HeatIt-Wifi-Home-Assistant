"""The parameter registry: one descriptor per observed parameter (§2.4, §3.3).

Expected wire strings are transcribed from the spec's serialisation column,
not derived from the registry, so the two encodings can disagree.
"""

import pytest

from custom_components.heatit_wifi_panel.registry import PARAMETERS

OBSERVED_WIRE_NAMES = {
    "panelMode",
    "heatingSetpoint",
    "ecoSetpoint",
    "minimumTemperatureLimit",
    "maximumTemperatureLimit",
    "sensorCalibration",
    "loadLimit",
    "activeDisplayBrightness",
    "standbyDisplayBrightness",
    "disableButtons",
    "temperatureDisplay",
    "sensorMode",
    "openWindowDetection",
}


def test_registry_holds_exactly_the_thirteen_observed_parameters() -> None:
    assert set(PARAMETERS) == OBSERVED_WIRE_NAMES
    assert all(descriptor.key == key for key, descriptor in PARAMETERS.items())


@pytest.mark.parametrize(
    ("key", "value", "wire"),
    [
        ("heatingSetpoint", 19.0, "19.0"),
        ("heatingSetpoint", 19, "19.0"),
        ("ecoSetpoint", 18.5, "18.5"),
        ("minimumTemperatureLimit", 5.0, "5.0"),
        ("maximumTemperatureLimit", 40.0, "40.0"),
        ("sensorCalibration", 1.1, "1.1"),
        ("sensorCalibration", -1.0, "-1.0"),
        # Float noise from caller arithmetic sits on the grid.
        ("sensorCalibration", 0.1 * 3, "0.3"),
        ("standbyDisplayBrightness", 50, "5"),
        ("standbyDisplayBrightness", 50.0, "5"),
        ("activeDisplayBrightness", 100, "10"),
        ("loadLimit", 600, "6"),
        ("loadLimit", 1500.0, "15"),
        ("panelMode", 2, "2"),
        ("disableButtons", 0, "0"),
        ("openWindowDetection", False, "false"),
        ("sensorMode", True, "true"),
        ("temperatureDisplay", True, "true"),
    ],
)
def test_serialisation_per_parameter(key: str, value: object, wire: str) -> None:
    assert PARAMETERS[key].encode(value) == wire


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("heatingSetpoint", 19.3),  # off the 0.5 grid
        ("heatingSetpoint", 4.5),  # below 5.0
        ("heatingSetpoint", 40.5),  # above 40.0
        ("minimumTemperatureLimit", 19.25),
        ("sensorCalibration", 1.15),  # off the 0.1 grid
        ("sensorCalibration", -6.1),
        ("sensorCalibration", 6.1),
        ("loadLimit", 0),
        ("loadLimit", 1600),
        ("loadLimit", 650),  # not a multiple of 100 W
        ("activeDisplayBrightness", 0),
        ("activeDisplayBrightness", 110),
        ("standbyDisplayBrightness", 55),
        ("standbyDisplayBrightness", -10),
        ("panelMode", 3),
        ("disableButtons", -1),
        ("panelMode", 1.5),
        ("panelMode", True),  # a bool is not an integer parameter
        ("openWindowDetection", 1),  # an int is not a boolean parameter
        ("openWindowDetection", "true"),
        ("heatingSetpoint", "19.0"),
    ],
)
def test_off_step_and_out_of_range_values_raise_locally(
    key: str, value: object
) -> None:
    with pytest.raises(ValueError, match=key):
        PARAMETERS[key].encode(value)


@pytest.mark.parametrize(
    ("key", "echo", "applied"),
    [
        ("heatingSetpoint", 19, 19.0),  # type-normalised by the device
        ("sensorCalibration", -1, -1.0),
        ("ecoSetpoint", 18.5, 18.5),
        ("loadLimit", 6, 600),  # scaled back to watts
        ("activeDisplayBrightness", 10, 100),
        ("standbyDisplayBrightness", 0, 0),
        ("panelMode", 1, 1),
        ("openWindowDetection", True, True),
        ("sensorMode", False, False),
    ],
)
def test_echo_is_coerced_to_the_declared_type_and_scaled(
    key: str, echo: object, applied: object
) -> None:
    result = PARAMETERS[key].decode(echo)
    assert result == applied
    assert type(result) is type(applied)


@pytest.mark.parametrize(
    ("key", "echo"),
    [
        ("heatingSetpoint", "19.0"),
        ("heatingSetpoint", None),
        ("panelMode", 1.5),
        ("panelMode", "1"),
        ("openWindowDetection", 1),
        ("openWindowDetection", "true"),
    ],
)
def test_an_unparseable_echo_decodes_to_none(key: str, echo: object) -> None:
    assert PARAMETERS[key].decode(echo) is None


def test_open_window_detection_is_written_flat_and_read_nested() -> None:
    descriptor = PARAMETERS["openWindowDetection"]
    assert descriptor.key == "openWindowDetection"
    assert descriptor.read_path == "parameters.OWD.openWindowDetection"
    others = {k: d.read_path for k, d in PARAMETERS.items() if k != descriptor.key}
    assert others == {k: f"parameters.{k}" for k in others}


def test_the_required_core_parameters_are_flagged() -> None:
    required = {key for key, d in PARAMETERS.items() if d.required}
    assert required == {"panelMode", "heatingSetpoint", "ecoSetpoint"}


@pytest.mark.parametrize(
    ("key", "step", "minimum", "maximum"),
    [
        ("heatingSetpoint", 0.5, 5.0, 40.0),
        ("ecoSetpoint", 0.5, 5.0, 40.0),
        ("minimumTemperatureLimit", 0.5, 5.0, 40.0),
        ("maximumTemperatureLimit", 0.5, 5.0, 40.0),
        ("sensorCalibration", 0.1, -6.0, 6.0),
        ("loadLimit", 100, 100, 1500),
        ("activeDisplayBrightness", 10, 10, 100),
        ("standbyDisplayBrightness", 10, 0, 100),
    ],
)
def test_user_facing_step_and_bounds(
    key: str, step: float, minimum: float, maximum: float
) -> None:
    descriptor = PARAMETERS[key]
    assert descriptor.step == step
    assert descriptor.minimum == minimum
    assert descriptor.maximum == maximum


@pytest.mark.parametrize(
    ("key", "choices"),
    [("panelMode", (0, 1, 2)), ("disableButtons", (0, 1, 2))],
)
def test_enumerated_parameters(key: str, choices: tuple[int, ...]) -> None:
    assert PARAMETERS[key].choices == choices


def test_a_scaled_integer_parameter_steps_by_its_scale() -> None:
    """Why an on-grid user value is always a whole number on the wire."""
    for descriptor in PARAMETERS.values():
        if descriptor.kind == "int" and descriptor.choices is None:
            assert descriptor.step == descriptor.scale, descriptor.key
