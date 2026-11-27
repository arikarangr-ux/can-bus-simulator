"""Very small physical models that produce believable signal values."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class BatteryModel:
    """400 V-class pack with a simple linear open-circuit voltage curve."""

    capacity_ah: float = 150.0
    soc: float = 80.0                  # %
    internal_resistance: float = 0.08  # ohm
    cell_temp: float = 28.0            # degC
    coolant_temp: float = 24.0         # degC

    def open_circuit_voltage(self) -> float:
        return 330.0 + 0.8 * self.soc  # 330 V empty .. 410 V full

    def step(self, current_a: float, dt_s: float) -> None:
        """Positive current = discharge."""
        self.soc -= (current_a * dt_s / 3600.0) / self.capacity_ah * 100.0
        self.soc = min(max(self.soc, 0.0), 100.0)
        heating = (current_a ** 2) * self.internal_resistance * dt_s / 50_000.0
        self.cell_temp += heating - (self.cell_temp - self.coolant_temp) * 0.002 * dt_s

    def terminal_voltage(self, current_a: float) -> float:
        return self.open_circuit_voltage() - current_a * self.internal_resistance


@dataclass
class DriveCycle:
    """Repeating accelerate / cruise / regen profile, 30 s long."""

    period_s: float = 30.0
    max_speed_rpm: float = 9000.0

    def motor_speed(self, t: float) -> float:
        phase = (t % self.period_s) / self.period_s
        return self.max_speed_rpm * math.sin(math.pi * phase)

    def motor_torque(self, t: float) -> float:
        phase = (t % self.period_s) / self.period_s
        # Positive while accelerating, negative (regen) while slowing down.
        return 250.0 * math.cos(math.pi * phase)

    def battery_current(self, t: float, pack_voltage: float) -> float:
        speed_rad_s = self.motor_speed(t) * 2 * math.pi / 60.0
        mech_power_w = self.motor_torque(t) * speed_rad_s
        efficiency = 0.92
        elec_power_w = mech_power_w / efficiency if mech_power_w > 0 else mech_power_w * efficiency
        return elec_power_w / max(pack_voltage, 1.0) + 8.0  # + auxiliary load
