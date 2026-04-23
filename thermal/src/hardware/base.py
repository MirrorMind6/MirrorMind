"""
Abstract base class for all sensor drivers.

Every driver — real or mock — must implement read() and close().
The rest of the pipeline only talks to this interface, so swapping
a mock for real hardware is a one-line change in runner.py.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..fusion import SensorReading


class SensorDriver(ABC):
    """Base class for all hardware/mock sensor drivers."""

    def __init__(self, sensor_id: str):
        self.sensor_id = sensor_id

    @abstractmethod
    def read(self) -> SensorReading:
        """Take one reading and return it as a SensorReading."""

    def close(self) -> None:
        """Release hardware resources. Override when needed."""

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(id={self.sensor_id!r})"
