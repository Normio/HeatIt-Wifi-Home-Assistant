"""Every key the flow and the coordinator can produce resolves in ``en.json``.

There is deliberately no ``strings.json``: its ``[%key:...%]`` syntax is a
build-time feature nothing resolves at runtime, so a custom integration shipping
one shows raw keys (§3.1). The authored artifact is a fully-expanded
``translations/en.json``, and an unresolved key here is a raw key in front of a
user.

**Wording is reviewed, not tested** (§8.6.4). What is asserted is that a key
resolves and that a message carries the placeholders its call site fills — an
`{expected_id}` the code never substitutes renders as literal braces to the
user, which is a bug and not a matter of phrasing. The key lists are
transcribed from §4 and §6 rather than read out of the module, so the two
encodings stay independent; the placeholder *names* are read from the code,
because agreeing on them is the whole point.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from custom_components.heatit_wifi_panel.const import foreign_panel_placeholders

TRANSLATIONS = (
    Path(__file__).parents[2]
    / "custom_components"
    / "heatit_wifi_panel"
    / "translations"
    / "en.json"
)

#: Every outcome §4 can reach, by section.
CONFIG_STEPS = ["user", "reconfigure"]
CONFIG_ERRORS = ["cannot_connect", "invalid_response"]
CONFIG_ABORTS = [
    "already_configured",
    "already_in_progress",
    "cannot_connect",
    "not_configured",
    "reconfigure_successful",
    "wrong_panel",
]
#: Every translation key §6 raises an exception under: the poll's four, then
#: §6.4's write-time table and the one local ``ServiceValidationError``.
EXCEPTIONS = [
    "cannot_connect",
    "invalid_response",
    "missing_field",
    "foreign_panel",
    "parameter_rejected",
    "unexpected_response",
    "set_temperature_while_off",
]

#: A write-time message and the placeholders its call site fills (§6.4). The
#: device's ``reason`` reaches the user verbatim, so the message has to have
#: somewhere to put it.
WRITE_PLACEHOLDERS = [
    ("parameter_rejected", ["parameter", "reason"]),
    ("unexpected_response", ["status"]),
]


@pytest.fixture(scope="module")
def translations() -> dict[str, Any]:
    """Read the shipped English strings."""
    document: dict[str, Any] = json.loads(TRANSLATIONS.read_text(encoding="utf-8"))
    return document


@pytest.mark.parametrize("step", CONFIG_STEPS)
def test_every_step_is_written(translations: dict[str, Any], step: str) -> None:
    form = translations["config"]["step"][step]
    assert form["title"]
    assert form["description"]
    assert form["data"] == {"host": "Host"}
    assert form["data_description"]["host"]


@pytest.mark.parametrize("error", CONFIG_ERRORS)
def test_every_form_error_is_written(translations: dict[str, Any], error: str) -> None:
    assert translations["config"]["error"][error]


@pytest.mark.parametrize("reason", CONFIG_ABORTS)
def test_every_abort_reason_is_written(
    translations: dict[str, Any], reason: str
) -> None:
    assert translations["config"]["abort"][reason]


@pytest.mark.parametrize("key", EXCEPTIONS)
def test_every_exception_message_is_written(
    translations: dict[str, Any], key: str
) -> None:
    assert translations["exceptions"][key]["message"]


def test_the_options_step_is_written(translations: dict[str, Any]) -> None:
    form = translations["options"]["step"]["init"]
    assert form["data"] == {"poll_interval": "Poll interval"}
    assert form["data_description"]["poll_interval"]


@pytest.mark.parametrize(
    "message",
    [
        "config.abort.wrong_panel",
        "exceptions.foreign_panel.message",
    ],
)
def test_a_foreign_panel_is_named_on_both_sides(
    translations: dict[str, Any], message: str
) -> None:
    """Naming one id leaves the user guessing which panel they are looking at.

    The names come from :func:`foreign_panel_placeholders`, the one builder both
    call sites use, so a renamed placeholder fails here rather than reaching a
    user as literal braces.
    """
    node: Any = translations
    for segment in message.split("."):
        node = node[segment]
    for placeholder in foreign_panel_placeholders("expected", "actual"):
        assert f"{{{placeholder}}}" in node


@pytest.mark.parametrize(("key", "placeholders"), WRITE_PLACEHOLDERS)
def test_a_write_failure_has_somewhere_to_put_the_panels_words(
    translations: dict[str, Any], key: str, placeholders: list[str]
) -> None:
    message = translations["exceptions"][key]["message"]
    for placeholder in placeholders:
        assert f"{{{placeholder}}}" in message


def test_the_missing_field_message_carries_the_path(
    translations: dict[str, Any],
) -> None:
    """§6.3's key needs the dotted path, which is why the client carries it."""
    assert "{field}" in translations["exceptions"]["missing_field"]["message"]
