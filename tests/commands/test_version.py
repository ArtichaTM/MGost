from mgost.cli import async_commands


async def test_version_runs():
    await async_commands.version()
