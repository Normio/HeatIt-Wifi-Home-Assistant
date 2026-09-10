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
    """The one attribute aiohttp reads off a ``stream_writer`` already sent."""

    output_size = 0


#: aiohttp 3.14 made ``stream_writer`` a required keyword on ``ClientResponse``.
#: aioresponses builds that object itself, and 0.7.9 — its newest release — does
#: not pass it, so every test on the ``mocked`` fixture raises ``TypeError`` on
#: the latest row. Read off the signature rather than pinned to a version, so
#: the floor row is left alone; and called through an unchecked ``Callable``,
#: because the keyword mypy must accept on one row does not exist on the other
#: and a ``type: ignore`` would then be unused on that one. Delete all three
#: names once aioresponses passes the keyword itself.
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
