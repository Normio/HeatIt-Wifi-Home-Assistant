"""Fixtures shared by the client tests: a real session, a mock wire, a client."""

import inspect
from functools import partial
from typing import TYPE_CHECKING, cast

import aiohttp
import pytest
from aioresponses import aioresponses

from custom_components.heatit_wifi_panel.api import HeatitClient

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Iterator

HOST = "panel.test"
JSON = "application/json"


@pytest.fixture
async def session() -> AsyncIterator[aiohttp.ClientSession]:
    async with aiohttp.ClientSession() as client_session:
        yield client_session


class _DrainedWriter:
    """The one attribute aiohttp reads from a ``stream_writer`` that has sent."""

    output_size = 0


#: aioresponses 0.7.9, its newest release, builds ``ClientResponse`` without
#: the ``stream_writer`` keyword that aiohttp 3.14 made required. Without this
#: patch every test on the ``mocked`` fixture raises ``TypeError`` on the
#: latest row. The check reads the signature instead of pinning a version, so
#: the floor row is left alone. The call goes through an unchecked
#: ``Callable`` because the keyword exists on one row and not the other, so a
#: ``type: ignore`` would be unused on one of them. Delete all three names
#: once aioresponses passes the keyword itself.
_NEEDS_STREAM_WRITER = (
    "stream_writer" in inspect.signature(aiohttp.ClientResponse.__init__).parameters
)
_CLIENT_RESPONSE = cast("Callable[..., aiohttp.ClientResponse]", aiohttp.ClientResponse)


@pytest.fixture
def mocked(monkeypatch: pytest.MonkeyPatch) -> Iterator[aioresponses]:
    if _NEEDS_STREAM_WRITER:
        monkeypatch.setattr(
            "aioresponses.core.ClientResponse",
            partial(_CLIENT_RESPONSE, stream_writer=_DrainedWriter()),
        )
    with aioresponses() as mock:
        yield mock


@pytest.fixture
def client(session: aiohttp.ClientSession) -> HeatitClient:
    return HeatitClient(HOST, session=session)
