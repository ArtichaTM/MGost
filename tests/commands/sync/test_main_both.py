import pytest
import respx

from ..utils import create_simple_environment


@pytest.mark.asyncio
async def test_trust_factors_correct(respx_mock: respx.MockRouter):
    environment = create_simple_environment(respx_mock)
    async with environment:
        pass
