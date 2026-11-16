import pytest

from pob_engine.service import EngineService


@pytest.fixture(scope="module")
def service():
    running = EngineService.start()
    try:
        yield running
    finally:
        running.close()
