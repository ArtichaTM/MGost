import pytest

from mgost.cli import async_commands


@pytest.mark.asyncio
async def test_version():
    await async_commands.version()
