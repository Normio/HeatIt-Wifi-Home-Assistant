"""Fixtures shared by the client tests: a real session, a mock wire, a client."""

from typing import TYPE_CHECKING

import aiohttp
import pytest
from aioresponses import aioresponses

from custom_components.heatit_wifi_panel.api import HeatitClient

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

HOST = "panel.test"
JSON = "application/json"


@pytest.fixture
async def session() -> AsyncIterator[aiohttp.ClientSession]:
    async with aiohttp.ClientSession() as client_session:
        yield client_session


@pytest.fixture
def mocked() -> Iterator[aioresponses]:
    with aioresponses() as mock:
        yield mock


@pytest.fixture
def client(session: aiohttp.ClientSession) -> HeatitClient:
    return HeatitClient(HOST, session=session)
