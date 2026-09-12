"""§9.2's rule tests that no platform suite owns, over every entity at once.

``quality_scale.yaml`` marks four rules ``done`` with this file as the
evidence: ``entity-unique-id``, ``has-entity-name``, ``entity-translations``
and ``icon-translations``. ``scripts/check_quality_scale.py`` fails the build
if this file goes away. The rest of §9.2's table points at the suites that
already held the fact:

- ``parallel-updates``, ``entity-category`` and its neighbours in
  ``test_entity.py``
- unloading in ``test_init.py``
- the second entry in ``test_config_flow.py``
- the download in ``test_diagnostics.py``

Every assertion runs over **all** the entities the integration ships, the
three that ship disabled included. Those are enabled in the registry and the
entry reloaded. So the objects the platforms build are inspected, not the
descriptions they were built from.
"""

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import async_get_platforms

from custom_components.heatit_wifi_panel.const import DOMAIN
from tests.integration.conftest import REFERENCE_DEVICE_ID, setup_entry

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity import Entity
    from pytest_homeassistant_custom_component.common import MockConfigEntry

INTEGRATION_DIR = Path(__file__).parents[2] / "custom_components" / "heatit_wifi_panel"

#: §5.2: the device id, a hyphen and the key, which is also the translation key.
UNIQUE_ID = re.compile(rf"^{re.escape(REFERENCE_DEVICE_ID)}-(?P<key>[a-z_]+)$")

#: What ``icons.json`` may hold: a Material Design Icons name, and nothing else.
ICON = re.compile(r"^mdi:[a-z0-9-]+$")


def read_json(name: str) -> dict[str, Any]:
    """Read one of the integration's shipped JSON documents."""
    document: dict[str, Any] = json.loads(
        (INTEGRATION_DIR / name).read_text(encoding="utf-8")
    )
    return document


def registered(hass: HomeAssistant, entry: MockConfigEntry) -> list[er.RegistryEntry]:
    """Return every registry entry the config entry owns."""
    return er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)


def shipped(hass: HomeAssistant) -> list[Entity]:
    """Return every entity object the platforms have added, across all platforms."""
    return [
        entity
        for platform in async_get_platforms(hass, DOMAIN)
        for entity in platform.entities.values()
    ]


def translation_keys(entities: list[Entity]) -> set[tuple[str, str]]:
    """Return each entity's ``(platform, translation_key)``, the two halves of a key."""
    return {
        (entity.platform.domain, entity.translation_key)
        for entity in entities
        if entity.platform is not None and entity.translation_key is not None
    }


def sets_attr_name(entity: Entity) -> bool:
    """Say whether one of *our* classes sets ``_attr_name`` on this entity.

    This asks the integration's own classes, not ``hasattr``. So a
    default that core might one day give ``Entity`` cannot make every entity
    look like the one that took the device's name.
    """
    return any(
        "_attr_name" in vars(cls)
        for cls in type(entity).__mro__
        if cls.__module__.startswith("custom_components.")
    )


@pytest.fixture
async def every_entity(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> list[Entity]:
    """Set the entry up with nothing disabled, and return the entity objects."""
    assert await setup_entry(hass, mock_config_entry)
    registry = er.async_get(hass)
    for entity in registered(hass, mock_config_entry):
        if entity.disabled:
            registry.async_update_entity(entity.entity_id, disabled_by=None)
    assert await hass.config_entries.async_reload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    entities = shipped(hass)
    assert len(entities) == len(registered(hass, mock_config_entry))
    return entities


@pytest.mark.usefixtures("patched_client")
async def test_every_unique_id_is_the_device_id_and_the_key(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """``{id}-{key}``, and the key half is the translation key (§5.2)."""
    assert await setup_entry(hass, mock_config_entry)

    entries = registered(hass, mock_config_entry)

    assert entries
    for entity in entries:
        matched = UNIQUE_ID.fullmatch(entity.unique_id)
        assert matched is not None, entity.unique_id
        assert matched["key"] == entity.translation_key


@pytest.mark.usefixtures("patched_client")
async def test_every_unique_id_survives_a_reload(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """A reload finds the same registry entries, and creates none."""
    assert await setup_entry(hass, mock_config_entry)
    before = {
        entity.entity_id: entity.unique_id
        for entity in registered(hass, mock_config_entry)
    }

    assert await hass.config_entries.async_reload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    after = {
        entity.entity_id: entity.unique_id
        for entity in registered(hass, mock_config_entry)
    }
    assert after == before


@pytest.mark.usefixtures("patched_client")
async def test_every_entity_has_entity_name(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    every_entity: list[Entity],
) -> None:
    """The registry's copy and the object's, both, on all of them."""
    assert all(entity.has_entity_name for entity in every_entity)
    assert all(entity.has_entity_name for entity in registered(hass, mock_config_entry))


@pytest.mark.usefixtures("patched_client")
async def test_no_entity_carries_a_name_or_an_icon_literal(
    every_entity: list[Entity],
) -> None:
    """Names come from ``translations/en.json`` and icons from ``icons.json``.

    ``_attr_name = None`` is allowed: it is how the climate entity marks itself
    the main feature. A string is not allowed. An entity description is the
    other place a literal could hide, so its two fields are held to the same
    rule.
    """
    for entity in every_entity:
        if sets_attr_name(entity):
            assert entity._attr_name is None, entity.entity_id  # noqa: SLF001 (the literal is the subject)
        assert getattr(entity, "_attr_icon", None) is None, entity.entity_id
        description = getattr(entity, "entity_description", None)
        if description is not None:
            assert not isinstance(description.name, str), entity.entity_id
            assert description.icon is None, entity.entity_id


@pytest.mark.usefixtures("patched_client")
async def test_every_translation_key_resolves_in_en_json(
    every_entity: list[Entity],
) -> None:
    """A key with nothing under it is a raw key in front of a user.

    Every entity has a node. Every entity but the one that took the device's
    name (``_attr_name = None``) has a ``name`` under it.
    """
    translations = read_json("translations/en.json")["entity"]

    for entity in every_entity:
        assert entity.platform is not None
        assert entity.translation_key is not None, entity.entity_id
        node = translations[entity.platform.domain][entity.translation_key]
        assert ("name" in node) is not sets_attr_name(entity), entity.entity_id


@pytest.mark.usefixtures("patched_client")
async def test_en_json_names_exactly_the_entities_that_ship(
    every_entity: list[Entity],
) -> None:
    """No orphan: a key in ``en.json`` that no entity carries is dead text."""
    translations = read_json("translations/en.json")["entity"]

    written = {
        (platform, key) for platform, keys in translations.items() for key in keys
    }

    assert written == translation_keys(every_entity)


@pytest.mark.usefixtures("patched_client")
async def test_icons_json_is_keyed_by_the_same_translation_keys(
    every_entity: list[Entity],
) -> None:
    """Every icon names a shipping entity, and every icon is an ``mdi:`` name.

    Not every entity has an icon, because a device class supplies one where
    there is no entry (§5.2). So the containment check runs one way. The
    frontend resolves these, not the state machine, so there is no state
    attribute to read back. What can be checked is that no key here is an
    orphan and no value a typo.
    """
    icons = read_json("icons.json")
    assert set(icons) == {"entity"}
    shipped_keys = translation_keys(every_entity)

    for platform, keys in icons["entity"].items():
        for key, icon in keys.items():
            assert (platform, key) in shipped_keys, f"{platform}.{key} ships no entity"
            assert ICON.match(icon["default"]), f"{platform}.{key}"
            for state, state_icon in icon.get("state", {}).items():
                assert ICON.match(state_icon), f"{platform}.{key}.{state}"
