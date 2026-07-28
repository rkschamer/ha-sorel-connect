"""Data models returned by the Sorel Connect API client."""

from dataclasses import dataclass


@dataclass
class SensorReading:
    """A single temperature sensor reading in degrees Celsius."""

    id: int
    value: float


@dataclass
class RelayReading:
    """A single relay reading as a percentage (0-100)."""

    id: int
    value: float


@dataclass
class SorelData:
    """A full snapshot of the controller state."""

    sensors: dict[int, SensorReading]
    relays: dict[int, RelayReading]
    logs: list[str]
