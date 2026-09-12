"""Integration tests: the config flow, the coordinator and the entities.

The seam is the **client** (§8.4). :class:`tests.fakes.FakeHeatitClient` is
patched in and fed the same observed bytes the client tests use, parsed by the
real parser. A real ``hass`` boots in process. Nothing here touches HTTP.
"""
