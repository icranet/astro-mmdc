import pytest
import respx

from astro_mmdc import MMDC


@pytest.fixture()
def mock_api():
    with respx.mock(base_url="https://mmdc.am") as api:
        yield api


@pytest.fixture()
def client():
    c = MMDC()
    yield c
    c.close()
