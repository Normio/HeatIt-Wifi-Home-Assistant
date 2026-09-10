"""The README's facts, each of which CI keeps from drifting (§11.3).

The README is one of three copies of the verified-firmware set — the others
are ``VERIFIED_FIRMWARES`` and ``tests/fixtures/observed/fw-*/`` — and the only
prose copy of the entity surface and the Home Assistant floor. Every one of
them is asserted against the artifact that owns it, so the README cannot
describe an integration that is not the one in the tree: all copies of a fact
or none.

One further assertion guards a promise made elsewhere and payable only here,
the static DHCP reservation of §4.5, and one guards the rule that sank a real
``hacs/default`` submission: no disclaimers.
"""

import importlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING

import pytest
from homeassistant.components.sensor import SensorEntityDescription
from homeassistant.const import Platform
from homeassistant.helpers.entity import Entity, EntityDescription

from custom_components.heatit_wifi_panel.const import DOMAIN, VERIFIED_FIRMWARES
from tests.conftest import observed_directories

if TYPE_CHECKING:
    from collections.abc import Iterator

REPO_ROOT = Path(__file__).resolve().parents[1]
README = REPO_ROOT / "README.md"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"
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

#: A released changelog section, ``## [0.1.0] - 2026-09-09``. Its arrival is
#: the release pull request, and so the moment the install section may exist.
RELEASED_VERSION = re.compile(r"^## \[\d+\.\d+\.\d+\]", re.MULTILINE)


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


def is_entity_description(item: object) -> bool:
    """Report whether this is a description, however core built its class.

    ``isinstance`` alone is not enough. Instantiating one of core's own
    description classes directly returns an instance of a *rebuilt* class under
    ``homeassistant.util.frozen_dataclass_compat`` which is not a subclass of
    ``EntityDescription`` at all; only a locally declared subclass is. Missing
    the first kind would let this guard pass over a whole platform in silence,
    which is the one failure a drift check must not have, so the ancestry is
    matched by name as well. A rename upstream reddens
    ``test_a_description_built_by_core_itself_is_recognised`` rather than
    quietly emptying the set.
    """
    return isinstance(item, EntityDescription) or any(
        ancestor.__name__ == EntityDescription.__name__
        for ancestor in type(item).__mro__
    )


def class_translation_key(entity: type[Entity]) -> str | None:
    """Return the key an entity class names itself with, if it names one."""
    for name in TRANSLATION_KEY_ATTRIBUTES:
        value = entity.__dict__.get(name)
        if isinstance(value, str):
            return value
    return None


def value_and_members(value: object) -> Iterator[object]:
    """Yield a value and, when it is a plain container, the members inside it.

    A platform declares its descriptions in whatever container reads best — a
    tuple, a single name, a mapping — and this test has no business dictating
    which, so it looks one level into any of them.
    """
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
        for item in value_and_members(value):
            if is_entity_description(item):
                keys.add(item.key)  # type: ignore[attr-defined]
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
        assert len(row) >= 2, (
            f"README entity row {row}: the entity, then the platform it is on"
        )
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


def test_the_install_section_waits_for_the_release_that_makes_it_true() -> None:
    released = RELEASED_VERSION.search(CHANGELOG.read_text(encoding="utf-8"))
    assert (section("Installation") is not None) == (released is not None), (
        "README: §11.3 writes the install section in the v0.1.0 release pull "
        "request and not before, because §11.1 forbids sharing the "
        "custom-repository URL until a release exists — without one HACS has "
        "no floor gate at all. The release pull request is the commit that "
        "first gives CHANGELOG.md a released version section, so the two "
        "arrive together or neither has"
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


class DescribedEntity(Entity):
    """A stand-in for a description-driven entity, named per instance."""


class NamedEntity(Entity):
    """A stand-in for the climate entity, which names itself on the class."""

    _attr_translation_key = "panel"


@dataclass(frozen=True, kw_only=True)
class LocalDescription(SensorEntityDescription):
    """A description declared in a platform module, as §3.5 requires."""


def module_holding(**values: object) -> ModuleType:
    """Build a stand-in platform module whose classes look locally defined."""
    module = ModuleType(__name__)
    for name, value in values.items():
        setattr(module, name, value)
    return module


@pytest.mark.parametrize(
    "description",
    [SensorEntityDescription(key="power"), LocalDescription(key="power")],
    ids=["built-by-core", "declared-locally"],
)
def test_a_description_built_by_core_itself_is_recognised(
    description: SensorEntityDescription,
) -> None:
    """Both kinds have to be found, however core built the class."""
    assert is_entity_description(description)


@pytest.mark.parametrize("item", ["power", 1, None, Entity])
def test_what_is_not_a_description_is_not_mistaken_for_one(item: object) -> None:
    assert not is_entity_description(item)


def test_declared_keys_finds_a_description_in_any_container() -> None:
    module = module_holding(
        SENSORS=(LocalDescription(key="power"),),
        ALONE=SensorEntityDescription(key="energy"),
        BY_NAME={"t": LocalDescription(key="temperature")},
    )
    assert declared_keys(module) == {"power", "energy", "temperature"}


def test_declared_keys_reads_the_key_an_entity_class_names_itself_with() -> None:
    """The literal survives ``Entity``'s metaclass; a rename upstream reddens here."""
    assert declared_keys(module_holding(HeatitClimate=NamedEntity)) == {"panel"}


def test_declared_keys_ignores_an_entity_class_that_names_no_key() -> None:
    assert declared_keys(module_holding(HeatitSensor=DescribedEntity)) == set()


def test_declared_keys_ignores_a_class_the_module_only_imported() -> None:
    """``Entity`` itself is in every platform module's namespace, and is not one."""
    assert declared_keys(module_holding(Entity=Entity)) == set()


@pytest.mark.parametrize(
    ("cell", "key"),
    [
        ("Comfort setpoint (`comfort_setpoint`)", "comfort_setpoint"),
        ("Heatit WiFi Panel (`panel`)", "panel"),
    ],
)
def test_an_entity_cell_carries_the_name_and_then_the_key(cell: str, key: str) -> None:
    match = ENTITY_CELL.match(cell)
    assert match is not None
    assert match["key"] == key


@pytest.mark.parametrize("cell", ["Comfort setpoint", "`comfort_setpoint`", ""])
def test_an_entity_cell_without_a_key_is_refused(cell: str) -> None:
    assert ENTITY_CELL.match(cell) is None
