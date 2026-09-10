"""The README's facts, each of which CI keeps from drifting (§11.3).

The README is one of three copies of the verified-firmware set — the others
are ``VERIFIED_FIRMWARES`` and ``tests/fixtures/observed/fw-*/`` — and the only
prose copy of the entity surface and the Home Assistant floor. Every one of
them is asserted against the artifact that owns it, so the README cannot
describe an integration that is not the one in the tree: all copies of a fact
or none.

Two further assertions guard promises made elsewhere and payable only here —
the WiFi6 signpost that [ADR-0001](../docs/adr/0001-no-fork-of-heatit-wifi6.md)
undertook to carry, and the static DHCP reservation of §4.5 — and one guards
the rule that sank a real ``hacs/default`` submission: no disclaimers.
"""

import importlib
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

from homeassistant.const import Platform
from homeassistant.helpers.entity import Entity, EntityDescription

from custom_components.heatit_wifi_panel.const import DOMAIN, VERIFIED_FIRMWARES
from tests.conftest import observed_directories

if TYPE_CHECKING:
    from collections.abc import Iterator
    from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[1]
README = REPO_ROOT / "README.md"
INTEGRATION_DIR = REPO_ROOT / "custom_components" / DOMAIN
PACKAGE = f"custom_components.{DOMAIN}"

#: Prose a `hacs/default` reviewer reads as "come back later". The 0.x version
#: number carries that message already, and hacs/default#8819 rejected a
#: submission for the README saying it in words. Matched case-insensitively
#: against the whole file with its whitespace flattened, so a phrase broken
#: across two lines is still one phrase. Hyphens are left alone and spelled out
#: where a pattern needs them: flattening those too would read "alpha-numeric"
#: as "alpha".
DISCLAIMERS = (
    r"alpha",
    r"beta",
    r"early access",
    r"experimental",
    r"not (?:yet )?production[ -]ready",
    r"not (?:yet )?ready",
    r"pending validation",
    r"pre[ -]?release",
    r"under development",
    r"unstable",
    r"use at your own risk",
    r"work in progress",
)

#: ``Entity``'s metaclass rewrites a class-level ``_attr_translation_key``
#: into a property and keeps the literal it was given under the second of these
#: names, so an entity class that names itself is read out of the class
#: dictionary rather than off the class.
TRANSLATION_KEY_ATTRIBUTES = ("_attr_translation_key", "__attr_translation_key")

#: A cell in the entity table's first column: the name a user sees, then the
#: key that names it in the translations and ends its unique id.
ENTITY_CELL = re.compile(r"^(?P<name>.+?)\s*\(`(?P<key>[a-z0-9_]+)`\)$")


def section(title: str) -> str | None:
    """Return the body of the ``## <title>`` section, or ``None`` if absent."""
    body = README.read_text(encoding="utf-8")
    match = re.search(
        rf"^## {re.escape(title)}\s*$(?P<body>.*?)(?=^## |\Z)",
        body,
        re.MULTILINE | re.DOTALL,
    )
    return match["body"] if match else None


def table_rows(body: str | None) -> list[list[str]]:
    """Return a Markdown table's data rows, header and rule dropped."""
    if body is None:
        return []
    rows = [
        [cell.strip() for cell in line.strip().strip("|").split("|")]
        for line in body.splitlines()
        if line.lstrip().startswith("|")
    ]
    return [
        row
        for row in rows[1:]
        if not all(set(cell) <= set("-: ") for cell in row if cell)
    ]


def class_translation_key(entity: type[Entity]) -> str | None:
    """Return the key an entity class names itself with, if it names one."""
    for name in TRANSLATION_KEY_ATTRIBUTES:
        value = entity.__dict__.get(name)
        if isinstance(value, str):
            return value
    return None


def unpack(value: object) -> Iterator[object]:
    """Yield a module-level value and, for a plain container, its members."""
    yield value
    if isinstance(value, tuple | list | set | frozenset):
        yield from value
    elif isinstance(value, dict):
        yield from value.values()


def declared_keys(module: ModuleType) -> set[str]:
    """Every entity key a platform module declares, however it declares it.

    The description-driven platforms carry one ``EntityDescription`` per
    entity, in whatever container they choose. The climate entity has no
    description and names itself with a class-level ``_attr_translation_key``,
    which §5.2 makes the same string as its unique-id suffix.
    """
    keys: set[str] = set()
    for value in vars(module).values():
        for item in unpack(value):
            if isinstance(item, EntityDescription):
                keys.add(item.key)
            elif (
                isinstance(item, type)
                and issubclass(item, Entity)
                and item.__module__ == module.__name__
            ):
                key = class_translation_key(item)
                if key is not None:
                    keys.add(key)
    return keys


def shipped_entities() -> set[tuple[str, str]]:
    """Every ``(platform, key)`` the integration ships, read from the modules."""
    found: set[tuple[str, str]] = set()
    for platform in Platform:
        if not (INTEGRATION_DIR / f"{platform.value}.py").is_file():
            continue
        module = importlib.import_module(f"{PACKAGE}.{platform.value}")
        found |= {(platform.value, key) for key in declared_keys(module)}
    return found


def documented_entities() -> set[tuple[str, str]]:
    """Every ``(platform, key)`` the README's ``## Entities`` table lists."""
    documented: set[tuple[str, str]] = set()
    for row in table_rows(section("Entities")):
        match = ENTITY_CELL.match(row[0])
        assert match, (
            f"README entity row {row[0]!r}: the first cell is the name a user "
            f"sees followed by the entity's key in backticks, as in "
            f"'Comfort setpoint (`comfort_setpoint`)'"
        )
        documented.add((row[1], match["key"]))
    return documented


def test_the_entity_table_lists_exactly_the_entities_that_ship() -> None:
    assert documented_entities() == shipped_entities(), (
        "The README's '## Entities' table and the platform modules disagree. "
        "A platform ships its README rows in the same pull request as its "
        "module: one row per entity, the name then the key in backticks, then "
        "the platform. While no platform ships, the section is absent."
    )


def test_the_verified_firmware_table_is_the_third_copy_of_the_fact() -> None:
    rows = table_rows(section("Verified firmware"))
    assert rows, "README: the '## Verified firmware' section holds a table"
    documented = {row[0].strip("` ") for row in rows}
    observed = {path.name.removeprefix("fw-") for path in observed_directories()}
    assert documented == set(VERIFIED_FIRMWARES)
    assert documented == observed


def test_every_verified_firmware_row_names_the_unit_it_was_verified_on() -> None:
    for row in table_rows(section("Verified firmware")):
        assert len(row) >= 2, f"README firmware row {row}: version, then the unit"
        assert row[1], f"README firmware row {row}: the unit is not blank"


def test_the_home_assistant_floor_matches_hacs_json() -> None:
    hacs = json.loads((REPO_ROOT / "hacs.json").read_text(encoding="utf-8"))
    floor = hacs["homeassistant"]
    assert floor in README.read_text(encoding="utf-8"), (
        f"README: the Home Assistant floor reads {floor}, as hacs.json declares "
        f"it — HACS refuses the download below that version"
    )


def test_the_readme_signposts_wifi6_thermostat_owners() -> None:
    assert "WiFi6" in README.read_text(encoding="utf-8"), (
        "README: ADR-0001 undertook a one-line signpost telling Heatit WiFi6 "
        "thermostat owners this integration is for the WiFi Panel wall heater. "
        "It is a routing aid, not an acknowledgement"
    )


def test_the_readme_recommends_a_static_dhcp_reservation() -> None:
    assert "DHCP reservation" in README.read_text(encoding="utf-8"), (
        "README: §4.5 leaves the host out of the options flow, so a static "
        "DHCP reservation is the answer the README owes the user"
    )


def test_the_readme_carries_no_disclaimer() -> None:
    prose = re.sub(r"\s+", " ", README.read_text(encoding="utf-8").lower())
    found = [pattern for pattern in DISCLAIMERS if re.search(rf"\b{pattern}\b", prose)]
    assert not found, (
        f"README: {found} reads as 'come back later'. The README states facts "
        f"and the 0.x version number carries the rest; hacs/default#8819 is a "
        f"submission rejected for exactly this prose"
    )
