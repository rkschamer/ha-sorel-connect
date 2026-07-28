"""Shared test fixtures."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.sorel_connect.api.models import (
    RelayReading,
    SensorReading,
    SorelData,
)


@pytest.fixture
def sample_data() -> SorelData:
    return SorelData(
        sensors={
            1: SensorReading(id=1, value=42.0),
            3: SensorReading(id=3, value=24.0),
        },
        relays={1: RelayReading(id=1, value=30.0)},
        logs=["newest", "middle", "oldest"],
    )


@pytest.fixture
def mock_client(sample_data: SorelData) -> MagicMock:
    client = MagicMock()
    client.login = AsyncMock()
    client.get_all = AsyncMock(return_value=sample_data)
    return client
