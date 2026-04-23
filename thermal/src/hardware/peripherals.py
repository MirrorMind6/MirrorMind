"""
Peripheral sensor drivers: VL53L0X (proximity), HC-SR501 PIR (motion),
BME280 (humidity + ambient temperature).

Each sensor has a real driver (Pi hardware) and a mock driver (simulation).

Real driver wiring
------------------
  VL53L0X   → I2C  (SDA=GPIO2, SCL=GPIO3)   — pip install adafruit-circuitpython-vl53l0x
  BME280     → I2C  (SDA=GPIO2, SCL=GPIO3)   — pip install adafruit-circuitpython-bme280
  HC-SR501   → GPIO (any free pin, e.g. 17)  — pip install RPi.GPIO

Swap mock → real in runner.py; nothing else changes.
"""

from __future__ import annotations

import time

import numpy as np

from ..fusion import SensorReading, SensorType
from .base import SensorDriver


# ============================================================
# VL53L0X  —  Time-of-Flight proximity sensor
# ============================================================

class VL53L0XDriver(SensorDriver):
    """
    Live VL53L0X driver (I2C, Raspberry Pi).

    TO ENABLE ON PI:
      pip install adafruit-circuitpython-vl53l0x
    """

    def __init__(self, sensor_id: str = "proximity_0"):
        super().__init__(sensor_id)
        try:
            import board
            import busio
            import adafruit_vl53l0x
            i2c = busio.I2C(board.SCL, board.SDA)
            self._sensor = adafruit_vl53l0x.VL53L0X(i2c)
        except Exception as exc:
            raise RuntimeError("VL53L0X not found. Check wiring.") from exc

    def read(self) -> SensorReading:
        distance_mm = self._sensor.range
        return SensorReading(
            sensor_id=self.sensor_id,
            sensor_type=SensorType.PROXIMITY,
            value=distance_mm / 10.0,   # → cm
            timestamp=time.monotonic(),
            unit="cm",
        )


class MockVL53L0X(SensorDriver):
    """
    Simulated proximity sensor.

    Stays at *idle_distance* cm until *trigger_after* seconds, then
    ramps down to *close_distance* cm (person walking toward sensor).
    """

    def __init__(
        self,
        sensor_id: str = "proximity_0",
        idle_distance: float = 300.0,
        close_distance: float = 40.0,
        trigger_after: float = 15.0,
        approach_duration: float = 5.0,
        noise_std: float = 2.0,
        seed: int = 1,
    ):
        super().__init__(sensor_id)
        self._idle = idle_distance
        self._close = close_distance
        self._trigger_after = trigger_after
        self._approach_duration = approach_duration
        self._noise_std = noise_std
        self._rng = np.random.default_rng(seed)
        self._start = time.monotonic()

    def read(self) -> SensorReading:
        t = time.monotonic() - self._start
        if t < self._trigger_after:
            dist = self._idle
        elif t < self._trigger_after + self._approach_duration:
            progress = (t - self._trigger_after) / self._approach_duration
            dist = self._idle + progress * (self._close - self._idle)
        else:
            dist = self._close

        dist += float(self._rng.normal(0, self._noise_std))
        return SensorReading(
            sensor_id=self.sensor_id,
            sensor_type=SensorType.PROXIMITY,
            value=max(0.0, dist),
            timestamp=time.monotonic(),
            unit="cm",
        )


# ============================================================
# HC-SR501  —  PIR motion sensor
# ============================================================

class PIRDriver(SensorDriver):
    """
    Live HC-SR501 PIR driver (single GPIO pin, Raspberry Pi).

    TO ENABLE ON PI:
      pip install RPi.GPIO
      Set gpio_pin to whichever BCM pin the sensor's OUT wire is connected to.
    """

    def __init__(self, sensor_id: str = "motion_0", gpio_pin: int = 17):
        super().__init__(sensor_id)
        self._pin = gpio_pin
        try:
            import RPi.GPIO as GPIO
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self._pin, GPIO.IN)
            self._gpio = GPIO
        except Exception as exc:
            raise RuntimeError(
                f"RPi.GPIO not available or pin {gpio_pin} not accessible."
            ) from exc

    def read(self) -> SensorReading:
        value = float(self._gpio.input(self._pin))
        return SensorReading(
            sensor_id=self.sensor_id,
            sensor_type=SensorType.MOTION,
            value=value,
            timestamp=time.monotonic(),
        )

    def close(self):
        try:
            self._gpio.cleanup(self._pin)
        except Exception:
            pass


class MockPIR(SensorDriver):
    """
    Simulated PIR sensor.

    Returns 0.0 until *trigger_after* seconds, then 1.0 for *active_duration*,
    with occasional false positives before the main trigger.
    """

    def __init__(
        self,
        sensor_id: str = "motion_0",
        trigger_after: float = 14.5,
        active_duration: float = 30.0,
        false_positive_rate: float = 0.02,
        seed: int = 2,
    ):
        super().__init__(sensor_id)
        self._trigger_after = trigger_after
        self._active_until = trigger_after + active_duration
        self._fp_rate = false_positive_rate
        self._rng = np.random.default_rng(seed)
        self._start = time.monotonic()

    def read(self) -> SensorReading:
        t = time.monotonic() - self._start
        if self._trigger_after <= t <= self._active_until:
            value = 1.0
        elif self._rng.random() < self._fp_rate:
            value = 1.0
        else:
            value = 0.0
        return SensorReading(
            sensor_id=self.sensor_id,
            sensor_type=SensorType.MOTION,
            value=value,
            timestamp=time.monotonic(),
        )


# ============================================================
# BME280  —  Humidity + ambient temperature
# ============================================================

class BME280Driver(SensorDriver):
    """
    Live BME280 driver (I2C, Raspberry Pi).

    TO ENABLE ON PI:
      pip install adafruit-circuitpython-bme280
    """

    def __init__(self, sensor_id: str = "humidity_0"):
        super().__init__(sensor_id)
        try:
            import board
            import busio
            import adafruit_bme280.basic as adafruit_bme280
            i2c = busio.I2C(board.SCL, board.SDA)
            self._sensor = adafruit_bme280.Adafruit_BME280_I2C(i2c)
        except Exception as exc:
            raise RuntimeError("BME280 not found. Check I2C wiring.") from exc

    def read(self) -> SensorReading:
        return SensorReading(
            sensor_id=self.sensor_id,
            sensor_type=SensorType.HUMIDITY,
            value=self._sensor.relative_humidity,
            timestamp=time.monotonic(),
            unit="%RH",
            metadata={"ambient_temp_c": self._sensor.temperature},
        )


class MockBME280(SensorDriver):
    """Simulated BME280 — stable humidity with small random walk."""

    def __init__(
        self,
        sensor_id: str = "humidity_0",
        base_humidity: float = 48.0,
        base_ambient: float = 21.5,
        noise_std: float = 0.5,
        seed: int = 3,
    ):
        super().__init__(sensor_id)
        self._humidity = base_humidity
        self._ambient = base_ambient
        self._noise_std = noise_std
        self._rng = np.random.default_rng(seed)

    def read(self) -> SensorReading:
        self._humidity += float(self._rng.normal(0, 0.1))
        self._humidity = float(np.clip(self._humidity, 20.0, 90.0))
        return SensorReading(
            sensor_id=self.sensor_id,
            sensor_type=SensorType.HUMIDITY,
            value=self._humidity + float(self._rng.normal(0, self._noise_std)),
            timestamp=time.monotonic(),
            unit="%RH",
            metadata={"ambient_temp_c": self._ambient + float(self._rng.normal(0, 0.1))},
        )
