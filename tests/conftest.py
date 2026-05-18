import asyncio
import sys
from pathlib import Path

import pytest

# Make pipeline importable from tests/
sys.path.insert(0, str(Path(__file__).parent.parent))

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture(scope="session")
def event_loop():
    """Session-wide event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
