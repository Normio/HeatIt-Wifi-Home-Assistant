"""Every key the flow and the coordinator can produce resolves in ``en.json``.

There is deliberately no ``strings.json``: its ``[%key:...%]`` syntax is a
build-time feature nothing resolves at runtime, so a custom integration shipping
one shows raw keys (§3.1). The authored artifact is a fully-expanded
``translations/en.json``, and an unresolved key here is a raw key in front of a
user.

The key lists are transcribed from §4 and §6 rather than read out of the
module, so this compares two independent encodings.
"""

import json
from pathlib import Path
from typing import Any

import pytest

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
#: Every translation key §6 raises an exception under.
EXCEPTIONS = ["cannot_connect", "invalid_response", "missing_field", "foreign_panel"]


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


def test_the_options_step_describes_the_poll_interval(
    translations: dict[str, Any],
) -> None:
    form = translations["options"]["step"]["init"]
    assert form["data"] == {"poll_interval": "Poll interval"}
    description = form["data_description"]["poll_interval"]
    assert "30" in description


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
    """Naming one id leaves the user guessing which panel they are looking at."""
    node: Any = translations
    for segment in message.split("."):
        node = node[segment]
    assert "{expected_id}" in node
    assert "{actual_id}" in node


def test_wrong_panel_says_a_replacement_is_a_new_device(
    translations: dict[str, Any],
) -> None:
    """The alternative is a button that quietly rewrites device identity (§4.5)."""
    assert "added as a new device" in translations["config"]["abort"]["wrong_panel"]


def test_the_missing_field_message_carries_the_path(
    translations: dict[str, Any],
) -> None:
    """§6.3's key needs the dotted path, which is why the client carries it."""
    assert "{field}" in translations["exceptions"]["missing_field"]["message"]
