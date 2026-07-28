from custom_components.sorel_connect.api.models import (
    RelayReading,
    SensorReading,
    SorelData,
)


def test_models_construct():
    data = SorelData(
        sensors={1: SensorReading(id=1, value=42.0)},
        relays={1: RelayReading(id=1, value=30.0)},
        logs=["newest", "older"],
    )
    assert data.sensors[1].value == 42.0
    assert data.relays[1].value == 30.0
    assert data.logs[0] == "newest"
